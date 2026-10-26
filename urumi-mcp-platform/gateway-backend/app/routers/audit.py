from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import AuditLog
from app.schemas import AuditLogResponse
from app.security import require_admin, AuthContext, compute_entry_hash

router = APIRouter(prefix="/audit", tags=["Tamper-Evident Audit Logs"])

@router.get("", response_model=List[AuditLogResponse])
async def get_audit_logs(
    limit: int = Query(50, ge=1, le=500),
    outcome: Optional[str] = Query(None),
    server: Optional[str] = Query(None),
    tool: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    stmt = select(AuditLog)
    if outcome:
        stmt = stmt.where(AuditLog.outcome == outcome)
    if server:
        stmt = stmt.where(AuditLog.server_slug == server)
    if tool:
        stmt = stmt.where(AuditLog.tool_name == tool)

    stmt = stmt.order_by(AuditLog.timestamp.desc()).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/verify-integrity")
async def verify_audit_integrity(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    """
    Cryptographically verifies the SHA-256 hash chain across all audit log entries
    to detect any database tampering, alteration, or row deletion.
    """
    stmt = select(AuditLog).order_by(AuditLog.id.asc())
    res = await db.execute(stmt)
    entries = res.scalars().all()

    if not entries:
        return {"intact": True, "entries_checked": 0, "message": "Audit trail is empty."}

    last_prev_hash: Optional[str] = None
    for i, entry in enumerate(entries):
        # 1. Check prev_hash links to prior entry's entry_hash
        if entry.prev_hash != last_prev_hash:
            return {
                "intact": False,
                "broken_at_id": entry.id,
                "error": f"Broken chain at record #{entry.id}: prev_hash does not match predecessor."
            }

        # 2. Recompute entry hash
        expected_hash = compute_entry_hash(
            prev_hash=entry.prev_hash,
            timestamp=entry.timestamp,
            user_id=entry.user_id,
            tool_name=entry.tool_name,
            outcome=entry.outcome
        )
        if entry.entry_hash != expected_hash:
            return {
                "intact": False,
                "broken_at_id": entry.id,
                "error": f"Hash mismatch at record #{entry.id}: entry content has been modified."
            }

        last_prev_hash = entry.entry_hash

    return {
        "intact": True,
        "entries_checked": len(entries),
        "latest_hash": entries[-1].entry_hash,
        "message": f"All {len(entries)} audit log entries verified intact. Cryptographic chain verified."
    }
