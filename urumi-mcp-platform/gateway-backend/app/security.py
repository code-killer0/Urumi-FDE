import os
import base64
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from cryptography.fernet import Fernet

from app.config import settings
from app.database import get_db
from app.models import User, ApiKey, UserRole, AuditOutcome

import bcrypt

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

# ── Credential Encryption at Rest (Fernet) ────────────────────────────────────
def _get_fernet() -> Fernet:
    """
    Returns a Fernet cipher instance.
    If settings.FERNET_KEY is already a valid 32-byte base64 Fernet key, uses it directly.
    Otherwise derives a deterministic 32-byte urlsafe-base64 key via SHA-256 for stability.
    """
    key = settings.FERNET_KEY or "urumi-fernet-secret-key-32-bytes!"
    try:
        decoded = base64.urlsafe_b64decode(key.encode("utf-8"))
        if len(decoded) == 32:
            return Fernet(key.encode("utf-8"))
    except Exception:
        pass
    raw = hashlib.sha256(key.encode("utf-8")).digest()
    derived = base64.urlsafe_b64encode(raw)
    return Fernet(derived)

def encrypt_credential(plain_text: str) -> str:
    """Encrypt upstream credential before persisting in DB."""
    if not plain_text:
        return ""
    f = _get_fernet()
    return f.encrypt(plain_text.encode("utf-8")).decode("utf-8")

def decrypt_credential(cipher_text: str) -> str:
    """Decrypt upstream credential at runtime."""
    if not cipher_text:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        return cipher_text  # fallback if stored unencrypted in dev

# ── Password Hashing (Native Bcrypt) ───────────────────────────────────────────
def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    # Truncate to 72 bytes as required by bcrypt specification
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")

# ── JWT Authentication ────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

# ── API Key Generation & Hashing ──────────────────────────────────────────────
def generate_api_key_pair() -> tuple[str, str, str]:
    """
    Generates (raw_key, key_prefix, key_hash).
    Format: urumi_sk_<32 hex chars> (total length 41 chars)
    Plaintext raw_key is returned ONCE to the user and never stored.
    """
    token_hex = secrets.token_hex(16)  # 32 hex chars
    raw_key = f"urumi_sk_{token_hex}"
    key_prefix = raw_key[:12]  # "urumi_sk_..."
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return raw_key, key_prefix, key_hash

def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()

# ── Sensitive Argument Redaction & Audit Tamper-Evidence ──────────────────────
SENSITIVE_FIELD_NAMES = {
    "password", "secret", "token", "key", "authorization", "credential",
    "access_token", "api_key", "consumer_secret", "credit_card", "cvv"
}

def redact_sensitive_dict(data: Any) -> Any:
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if any(s in k.lower() for s in SENSITIVE_FIELD_NAMES):
                redacted[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                redacted[k] = redact_sensitive_dict(v)
            else:
                redacted[k] = v
        return redacted
    elif isinstance(data, list):
        return [redact_sensitive_dict(item) for item in data]
    return data

def normalize_timestamp_str(ts: Any) -> str:
    if isinstance(ts, datetime):
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
        return ts.strftime("%Y-%m-%d %H:%M:%S.%f")
    return str(ts)

def compute_entry_hash(
    prev_hash: Optional[str],
    timestamp: Any,
    user_id: Optional[int],
    tool_name: Optional[str],
    outcome: str
) -> str:
    ts_str = normalize_timestamp_str(timestamp)
    payload = f"{prev_hash or 'GENESIS'}|{ts_str}|{user_id}|{tool_name}|{outcome}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

# ── Auth Context & Dependency Resolution ──────────────────────────────────────
class AuthContext:
    def __init__(
        self,
        user: Optional[User] = None,
        api_key: Optional[ApiKey] = None,
        auth_type: str = "anonymous",
    ):
        self.user = user
        self.api_key = api_key
        self.auth_type = auth_type  # "jwt", "api_key", "chat_session", "anonymous"

    @property
    def is_authenticated(self) -> bool:
        return self.auth_type in ("jwt", "api_key", "chat_session")

    @property
    def is_admin(self) -> bool:
        return bool(self.user and self.user.role == UserRole.ADMIN.value)

    @property
    def user_id(self) -> Optional[int]:
        return self.user.id if self.user else None

    @property
    def user_email(self) -> Optional[str]:
        return self.user.email if self.user else None

    @property
    def user_role(self) -> str:
        return self.user.role if self.user else "anonymous"

async def authenticate_token(
    token: str,
    db: AsyncSession
) -> tuple[Optional[AuthContext], Optional[str]]:
    """
    Validates a raw token (API key or JWT).
    Returns (AuthContext, None) on success.
    Returns (AuthContext, "REVOKED") if the API key exists but is revoked.
    Returns (None, "INVALID") if token could not be verified.
    """
    if not token:
        return None, "INVALID"

    token = token.strip()

    # 1. Check if token matches an API key in the database
    key_h = hash_api_key(token)
    stmt = select(ApiKey).where(ApiKey.key_hash == key_h)
    res = await db.execute(stmt)
    api_key = res.scalar_one_or_none()

    if api_key:
        u_stmt = select(User).where(User.id == api_key.user_id)
        user = (await db.execute(u_stmt)).scalar_one_or_none()
        auth_context = AuthContext(user=user, api_key=api_key, auth_type="api_key")

        if api_key.revoked_at is not None:
            return auth_context, "REVOKED"

        api_key.last_used_at = datetime.now(timezone.utc)
        await db.commit()
        return auth_context, None

    # 2. Check if token is a valid JWT
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id:
            u_stmt = select(User).where(User.id == int(user_id))
            user = (await db.execute(u_stmt)).scalar_one_or_none()
            if user:
                return AuthContext(user=user, auth_type="jwt"), None
    except (JWTError, ValueError):
        pass

    return None, "INVALID"

async def get_current_auth(
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key_header: Optional[str] = Security(api_key_header_scheme),
    db: AsyncSession = Depends(get_db)
) -> AuthContext:
    raw_token = None
    if bearer and bearer.credentials:
        raw_token = bearer.credentials
    elif api_key_header:
        raw_token = api_key_header

    if raw_token:
        auth_context, error_status = await authenticate_token(raw_token, db)
        if error_status == "REVOKED":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has been revoked."
            )
        if not auth_context or not auth_context.is_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key or token."
            )
        return auth_context

    return AuthContext(auth_type="anonymous")

def require_auth(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
    if not auth.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a valid Bearer token or X-API-Key header."
        )
    return auth

def require_admin(auth: AuthContext = Depends(require_auth)) -> AuthContext:
    if not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required."
        )
    return auth
