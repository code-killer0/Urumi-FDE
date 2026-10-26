import os
from typing import List, Optional, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from cryptography.fernet import Fernet

class Settings(BaseSettings):
    PROJECT_NAME: str = "Urumi High-Availability MCP Gateway"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Security & Encryption
    JWT_SECRET: str = "urumi-super-secret-production-grade-jwt-signing-key-32charsmin"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    # Default 32-byte url-safe base64 key for Fernet credential encryption at rest
    FERNET_KEY: str = "k8s-mcp-gateway-production-fernet-key-32b="

    # Database: Supports SQLite (PVC) and PostgreSQL (DATABASE_URL)
    DATABASE_URL: str = "sqlite+aiosqlite:///./urumi_gateway.db"

    # Redis (Optional)
    REDIS_URL: Optional[str] = None

    # Rate Limiting (Sliding Window Token Bucket)
    RATE_LIMIT_GLOBAL_PER_MIN: int = 600
    RATE_LIMIT_PER_KEY_PER_MIN: int = 120
    RATE_LIMIT_ANONYMOUS_PER_MIN: int = 30

    # SSRF Protection
    ALLOW_INTERNAL_IPS: bool = True
    ALLOWED_HOST_DOMAINS: List[str] = [
        "localhost",
        "127.0.0.1",
        "woocommerce-mcp",
        "promos-analytics-mcp",
        "ops-notifier-mcp",
        "woo",
        "promos",
        "ops",
        "woocommerce-mcp.urumi-system.svc.cluster.local",
        "promos-analytics-mcp.urumi-system.svc.cluster.local",
        "ops-notifier-mcp.urumi-system.svc.cluster.local",
        "woo.urumi-system.svc.cluster.local",
        "promos.urumi-system.svc.cluster.local",
        "ops.urumi-system.svc.cluster.local"
    ]

    # Meta-Tool Search / Scale Mode
    SCALE_MODE_ENABLED: bool = False

    # Upstream MCP Timeouts & Probing
    UPSTREAM_TIMEOUT_LIST_SECONDS: float = 2.5
    UPSTREAM_TIMEOUT_CALL_SECONDS: float = 10.0
    HEALTH_CHECK_INTERVAL_SECONDS: float = 5.0
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: float = 30.0

    # Multi-Store Kubernetes Provisioning (Phase 2 Bonus)
    MAX_STORES_PER_USER: int = 3
    PROVISION_TIMEOUT_SECONDS: int = 300
    K8S_NAMESPACE_PREFIX: str = "urumi-store-"
    HELM_CHART_PATH: str = "/app/charts/woo-store-tenant" if os.path.isdir("/app/charts/woo-store-tenant") else os.path.abspath(os.path.join(os.path.dirname(__file__), "../../charts/woo-store-tenant"))
    GATEWAY_NAMESPACE: str = "urumi-system"
    GATEWAY_INGRESS_DOMAIN: str = "127.0.0.1.nip.io"
    RECONCILIATION_INTERVAL_SECONDS: float = 15.0

    # LLM Settings (OpenAI, Gemini, or local Ollama/vLLM)
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_MODEL: str = "gemini-flash-lite-latest"
    LLM_TIMEOUT_SECONDS: float = 60.0

    # Initial User Seeds
    ADMIN_EMAIL: str = "admin@urumi.local"
    ADMIN_PASSWORD: str = "UrumiAdmin2026!"
    MEMBER_EMAIL: str = "member@urumi.local"
    MEMBER_PASSWORD: str = "UrumiMember2026!"

    # Initial Upstream MCP Server Seeds
    WOO_MCP_URL: str = "http://127.0.0.1:8001"
    WOO_MCP_TOKEN: str = "dev-token-woo"

    PROMOS_MCP_URL: str = "http://127.0.0.1:8002"
    PROMOS_MCP_TOKEN: str = "dev-token-promos"

    OPS_MCP_URL: str = "http://127.0.0.1:8003"
    OPS_MCP_TOKEN: str = "dev-token-ops"

    model_config = SettingsConfigDict(
        env_file=[
            ".env",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../.env")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.env"))
        ],
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    def model_post_init(self, __context: Any) -> None:
        if self.GEMINI_API_KEY:
            self.GEMINI_API_KEY = self.GEMINI_API_KEY.strip()
        if self.GOOGLE_API_KEY:
            self.GOOGLE_API_KEY = self.GOOGLE_API_KEY.strip()
        if self.OPENAI_API_KEY:
            self.OPENAI_API_KEY = self.OPENAI_API_KEY.strip()

settings = Settings()
