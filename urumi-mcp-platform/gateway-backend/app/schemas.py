from typing import List, Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

# ── User & Auth Schemas ───────────────────────────────────────────────────────
class UserBase(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    name: Optional[str] = None
    role: str = "member"

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserResponse(UserBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    password: str

# ── API Key Schemas ───────────────────────────────────────────────────────────
class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)

class ApiKeyCreatedResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    raw_api_key: str  # Displayed ONLY ONCE upon creation!
    created_at: datetime

class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    revoked_at: Optional[datetime] = None
    created_at: datetime
    last_used_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

# ── Upstream Server Schemas ───────────────────────────────────────────────────
class UpstreamServerCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., pattern=r"^[a-z0-9_]+$", min_length=2, max_length=100)
    url: Optional[str] = Field(default=None, max_length=500)
    auth_header_name: str = Field(default="Authorization")
    credential: Optional[str] = Field(default=None, description="Plaintext bearer token (will be encrypted at rest)")
    enabled: bool = True
    is_hosted: bool = False
    container_image: Optional[str] = None
    env_vars: Optional[Dict[str, str]] = None

class UpstreamServerUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    credential: Optional[str] = None
    enabled: Optional[bool] = None

class UpstreamServerResponse(BaseModel):
    id: int
    name: str
    slug: str
    url: str
    auth_header_name: str
    enabled: bool
    is_hosted: bool
    container_image: Optional[str] = None
    status: str
    last_error: Optional[str] = None
    latency_ms: float
    total_calls: int
    failed_calls: int
    cached_tools: List[Dict[str, Any]]
    last_health_check: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# ── Provisioned Store Schemas (Phase 2 Bonus) ─────────────────────────────────
class ProvisionedStoreCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., pattern=r"^[a-z0-9-]{3,20}$", description="Store subdomain slug e.g. electronics-demo")

class ProvisionedStoreResponse(BaseModel):
    id: int
    name: str
    slug: str
    namespace: str
    owner_user_id: int
    status: str
    store_url: Optional[str] = None
    mcp_server_id: Optional[int] = None
    mcp_server_slug: Optional[str] = None
    error_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# ── Audit Log Schemas ─────────────────────────────────────────────────────────
class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    auth_method: str
    server_slug: Optional[str] = None
    tool_name: Optional[str] = None
    arguments_redacted: Optional[Dict[str, Any]] = None
    duration_ms: float
    outcome: str
    error_message: Optional[str] = None
    prev_hash: Optional[str] = None
    entry_hash: str

    model_config = ConfigDict(from_attributes=True)

# ── Chat & Conversation Schemas ───────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None

class ChatResponse(BaseModel):
    message: Dict[str, Any]
    tool_execution_trace: List[Dict[str, Any]] = []
