import time
import re
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
import httpx
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.config import settings
from app.models import UpstreamServer, ServerStatus
from app.security import decrypt_credential

logger = logging.getLogger("upstream-manager")

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"<\|system\|>|<\|assistant\|>|<\|user\|>", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*(?:system|assistant)\s*:", re.IGNORECASE),
    re.compile(r"</?system>", re.IGNORECASE),
    re.compile(r"\[/?INST\]", re.IGNORECASE),
]

def sanitize_description(raw: str) -> str:
    """Strip prompt injection markers and truncate description to 400 chars."""
    if not raw:
        return ""
    sanitized = raw
    for pat in PROMPT_INJECTION_PATTERNS:
        sanitized = pat.sub("[FILTERED]", sanitized)
    sanitized = " ".join(sanitized.split())
    if len(sanitized) > 400:
        sanitized = sanitized[:397] + "..."
    return sanitized

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def record_success(self):
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.error(f"Circuit Breaker tripped to OPEN after {self.failure_count} consecutive failures")

    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.monotonic() - self.last_failure_time >= self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit Breaker entering HALF_OPEN trial state")
                return True
            return False
        if self.state == "HALF_OPEN":
            return True
        return False

class UpstreamManager:
    """
    Manages upstream MCP servers, circuit breaking, dynamic tool synchronization,
    and Streamable HTTP JSON-RPC 2.0 communication.
    """
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.http_client: Optional[httpx.AsyncClient] = None

    async def get_http_client(self) -> httpx.AsyncClient:
        if self.http_client is None or self.http_client.is_closed:
            self.http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.UPSTREAM_TIMEOUT_CALL_SECONDS, connect=2.0),
                limits=httpx.Limits(max_keepalive_connections=50, max_connections=200)
            )
        return self.http_client

    def get_circuit_breaker(self, slug: str) -> CircuitBreaker:
        if slug not in self.circuit_breakers:
            self.circuit_breakers[slug] = CircuitBreaker(
                failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                recovery_timeout=settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT
            )
        return self.circuit_breakers[slug]

    async def probe_and_sync_server(self, server: UpstreamServer, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Probes an upstream server via Streamable HTTP with a strict 2.5s timeout on tools/list.
        If the pod is down or slow, catches error, marks status='Unreachable', updates last_error,
        and returns cached tools (or empty list) without failing the gateway.
        """
        if not server.enabled:
            return []

        breaker = self.get_circuit_breaker(server.slug)
        if not breaker.can_execute():
            logger.warning(f"Circuit breaker OPEN for server '{server.slug}'. Skipping live probe.")
            return server.cached_tools or []

        client = await self.get_http_client()
        target_url = f"{server.url.rstrip('/')}/mcp"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if server.encrypted_credential:
            token = decrypt_credential(server.encrypted_credential)
            if token:
                headers[server.auth_header_name] = f"Bearer {token}" if "bearer" not in token.lower() else token

        payload = {
            "jsonrpc": "2.0",
            "id": f"probe_{int(time.time())}",
            "method": "tools/list",
            "params": {}
        }

        t0 = time.monotonic()
        try:
            resp = await client.post(
                target_url,
                json=payload,
                headers=headers,
                timeout=settings.UPSTREAM_TIMEOUT_LIST_SECONDS
            )
            elapsed_ms = (time.monotonic() - t0) * 1000

            if resp.status_code == 200:
                data = resp.json()
                raw_tools = data.get("result", {}).get("tools", [])
                sanitized_tools = []
                for t in raw_tools:
                    st = dict(t)
                    st["description"] = sanitize_description(t.get("description", ""))
                    sanitized_tools.append(st)

                server.status = ServerStatus.CONNECTED.value
                server.last_error = None
                server.latency_ms = round(elapsed_ms, 2)
                server.cached_tools = sanitized_tools
                server.last_health_check = datetime.now(timezone.utc)
                breaker.record_success()
                await db.commit()
                return sanitized_tools
            else:
                err_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                server.status = ServerStatus.UNREACHABLE.value
                server.last_error = err_msg
                server.last_health_check = datetime.now(timezone.utc)
                breaker.record_failure()
                await db.commit()
                logger.error(f"Health check failed for {server.slug}: {err_msg}")
                return server.cached_tools or []

        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {str(exc)}"
            server.status = ServerStatus.UNREACHABLE.value
            server.last_error = err_msg
            server.last_health_check = datetime.now(timezone.utc)
            breaker.record_failure()
            await db.commit()
            logger.warning(f"Upstream server {server.slug} unreachable: {err_msg}")
            return server.cached_tools or []

    async def execute_tool_call(
        self,
        server: UpstreamServer,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes tools/call on upstream server with strict 10.0s timeout.
        Updates latency, total_calls, and failed_calls on the server model.
        """
        breaker = self.get_circuit_breaker(server.slug)
        if not breaker.can_execute():
            raise RuntimeError(f"Circuit breaker is OPEN for upstream server '{server.slug}'. Service temporarily unavailable.")

        client = await self.get_http_client()
        target_url = f"{server.url.rstrip('/')}/mcp"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if server.encrypted_credential:
            token = decrypt_credential(server.encrypted_credential)
            if token:
                headers[server.auth_header_name] = f"Bearer {token}" if "bearer" not in token.lower() else token

        payload = {
            "jsonrpc": "2.0",
            "id": f"call_{int(time.time()*1000)}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        t0 = time.monotonic()
        try:
            resp = await client.post(
                target_url,
                json=payload,
                headers=headers,
                timeout=settings.UPSTREAM_TIMEOUT_CALL_SECONDS
            )
            elapsed_ms = (time.monotonic() - t0) * 1000
            server.total_calls += 1
            server.latency_ms = round(elapsed_ms, 2)

            if resp.status_code == 200:
                breaker.record_success()
                data = resp.json()
                if "error" in data:
                    server.failed_calls += 1
                    raise RuntimeError(f"Upstream MCP error: {data['error'].get('message')}")
                return {"result": data.get("result", {}), "latency_ms": elapsed_ms}
            else:
                server.failed_calls += 1
                breaker.record_failure()
                raise RuntimeError(f"Upstream returned HTTP {resp.status_code}: {resp.text[:300]}")

        except (asyncio.TimeoutError, httpx.TimeoutException):
            server.total_calls += 1
            server.failed_calls += 1
            breaker.record_failure()
            server.status = ServerStatus.UNREACHABLE.value
            server.last_error = f"Timeout during tool execution (>{settings.UPSTREAM_TIMEOUT_CALL_SECONDS}s)"
            raise TimeoutError(f"Tool call to '{server.slug}__{tool_name}' timed out after {settings.UPSTREAM_TIMEOUT_CALL_SECONDS}s")
        except Exception as e:
            server.total_calls += 1
            server.failed_calls += 1
            breaker.record_failure()
            server.last_error = str(e)
            raise

upstream_manager = UpstreamManager()
