import time
import logging
from typing import Dict, Tuple, Optional
from collections import defaultdict
from fastapi import Request, HTTPException, status
from app.config import settings

logger = logging.getLogger("urumi-rate-limiter")

class TokenBucket:
    def __init__(self, capacity: int, fill_rate: float):
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.fill_rate = float(fill_rate) # tokens per second
        self.last_update = time.monotonic()

    def consume(self, tokens: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_update
        self.last_update = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

class RateLimiter:
    """
    High-performance sliding token bucket rate limiter with automatic stale-bucket pruning.
    Pluggable with Redis for multi-pod Kubernetes gateway deployments.
    """
    def __init__(self):
        self.buckets: Dict[str, TokenBucket] = {}
        self._last_cleanup = time.monotonic()

    def cleanup_stale_buckets(self, max_idle_seconds: float = 300.0) -> None:
        now = time.monotonic()
        stale_keys = [
            k for k, b in self.buckets.items()
            if (now - b.last_update) > max_idle_seconds
        ]
        for k in stale_keys:
            del self.buckets[k]
        self._last_cleanup = now

    def get_bucket(self, identifier: str, max_per_minute: int) -> TokenBucket:
        now = time.monotonic()
        if now - self._last_cleanup > 60.0 or len(self.buckets) > 2000:
            self.cleanup_stale_buckets()

        if identifier not in self.buckets:
            fill_rate = max_per_minute / 60.0
            self.buckets[identifier] = TokenBucket(capacity=max_per_minute, fill_rate=fill_rate)
        return self.buckets[identifier]

    def check_rate_limit(self, identifier: str, max_per_minute: int) -> Tuple[bool, int]:
        bucket = self.get_bucket(identifier, max_per_minute)
        allowed = bucket.consume(1.0)
        remaining = int(bucket.tokens)
        return allowed, remaining

rate_limiter = RateLimiter()

def enforce_rate_limit(request: Request, client_id: str, limit_per_minute: int):
    allowed, remaining = rate_limiter.check_rate_limit(client_id, limit_per_minute)
    if not allowed:
        logger.warning(f"Rate limit exceeded for client {client_id} (limit: {limit_per_minute}/min)")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {limit_per_minute} requests per minute allowed."
        )
