from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import ApiKey, User
from app.schemas import ApiKeyCreate, ApiKeyResponse, ApiKeyCreatedResponse
from app.security import require_auth, AuthContext, generate_api_key_pair

router = APIRouter(prefix="/keys", tags=["API Key Management"])

@router.get("", response_model=List[ApiKeyResponse])
async def list_keys(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_auth)
):
    if auth.is_admin:
        stmt = select(ApiKey).order_by(ApiKey.id.desc())
    else:
        stmt = select(ApiKey).where(ApiKey.user_id == auth.user.id).order_by(ApiKey.id.desc())
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    key_in: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_auth)
):
    if not auth.user:
        raise HTTPException(status_code=400, detail="Cannot generate an API key using an existing API key.")

    raw_key, prefix, key_h = generate_api_key_pair()

    new_key = ApiKey(
        user_id=auth.user.id,
        name=key_in.name,
        key_prefix=prefix,
        key_hash=key_h,
        revoked_at=None,
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)

    return ApiKeyCreatedResponse(
        id=new_key.id,
        name=new_key.name,
        key_prefix=new_key.key_prefix,
        raw_api_key=raw_key,  # Returned ONCE upon creation and never stored!
        created_at=new_key.created_at
    )

@router.delete("/{key_id}", status_code=status.HTTP_200_OK)
async def revoke_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_auth)
):
    """Instantly revokes an API key, timestamping revoked_at."""
    stmt = select(ApiKey).where(ApiKey.id == key_id)
    key = (await db.execute(stmt)).scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found.")

    if not auth.is_admin and key.user_id != auth.user.id:
        raise HTTPException(status_code=403, detail="Not authorized to revoke this API key.")

    key.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": f"API key '{key.name}' ({key.key_prefix}...) revoked successfully."}
