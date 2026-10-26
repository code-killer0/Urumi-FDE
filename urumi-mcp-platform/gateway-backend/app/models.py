import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, Enum, ForeignKey, Float, JSON
)
from sqlalchemy.orm import relationship
from app.database import Base

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MEMBER = "member"

class ServerStatus(str, enum.Enum):
    CONNECTED = "Connected"
    UNREACHABLE = "Unreachable"
    DISABLED = "Disabled"

class StoreStatus(str, enum.Enum):
    PROVISIONING = "Provisioning"
    READY = "Ready"
    FAILED = "Failed"
    DELETING = "Deleting"

class AuditOutcome(str, enum.Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    REJECTED_REVOKED_KEY = "REJECTED_REVOKED_KEY"
    REJECTED_FORBIDDEN = "REJECTED_FORBIDDEN"
    REJECTED_DISABLED = "REJECTED_DISABLED"
    RATE_LIMITED = "RATE_LIMITED"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default=UserRole.MEMBER.value, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")
    stores = relationship("ProvisionedStore", back_populates="owner", cascade="all, delete-orphan")

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    key_prefix = Column(String(16), index=True, nullable=False)  # First 12 chars e.g. urumi_sk_...
    key_hash = Column(String(64), unique=True, index=True, nullable=False)  # SHA-256 hex digest
    revoked_at = Column(DateTime(timezone=True), nullable=True)  # Nullable timestamp for instant revocation
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="api_keys")

class UpstreamServer(Base):
    __tablename__ = "upstream_servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)  # regex: ^[a-z0-9_]+$
    url = Column(String(500), nullable=False)  # e.g. http://woocommerce-mcp:8001
    auth_header_name = Column(String(50), default="Authorization", nullable=False)
    encrypted_credential = Column(Text, nullable=True)  # Fernet symmetric ciphertext
    enabled = Column(Boolean, default=True, nullable=False)
    is_hosted = Column(Boolean, default=False, nullable=False)
    container_image = Column(String(255), nullable=True)
    store_id = Column(Integer, nullable=True)
    status = Column(String(30), default=ServerStatus.CONNECTED.value, nullable=False)
    last_error = Column(Text, nullable=True)
    latency_ms = Column(Float, default=0.0, nullable=False)
    total_calls = Column(Integer, default=0, nullable=False)
    failed_calls = Column(Integer, default=0, nullable=False)
    cached_tools = Column(JSON, default=list, nullable=False)
    last_health_check = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class ToolPermissionPolicy(Base):
    __tablename__ = "tool_permission_policies"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(20), default=UserRole.MEMBER.value, nullable=False)
    tool_pattern = Column(String(150), nullable=False)  # e.g. *__create_product, *__update_order_status
    allowed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_email = Column(String(255), nullable=True)
    user_role = Column(String(20), nullable=True)
    auth_method = Column(String(30), nullable=False)  # "api_key" | "chat_session"
    server_slug = Column(String(100), nullable=True)
    tool_name = Column(String(100), nullable=True)
    arguments_redacted = Column(JSON, nullable=True)
    duration_ms = Column(Float, default=0.0, nullable=False)
    outcome = Column(String(50), nullable=False)  # SUCCESS, ERROR, TIMEOUT, REJECTED_REVOKED_KEY, REJECTED_FORBIDDEN, REJECTED_DISABLED, RATE_LIMITED
    error_message = Column(Text, nullable=True)
    prev_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=False)

    user = relationship("User", back_populates="audit_logs")

class ProvisionedStore(Base):
    __tablename__ = "provisioned_stores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)
    namespace = Column(String(100), nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(30), default=StoreStatus.PROVISIONING.value, nullable=False)
    store_url = Column(String(500), nullable=True)
    mcp_server_id = Column(Integer, ForeignKey("upstream_servers.id", ondelete="SET NULL"), nullable=True)
    error_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    owner = relationship("User", back_populates="stores")
    mcp_server = relationship("UpstreamServer")
