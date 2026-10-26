import json
import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models import (
    UpstreamServer, AuditLog, ServerStatus, UserRole, AuditOutcome,
    ToolPermissionPolicy, ApiKey, User
)
from app.security import (
    get_current_auth, AuthContext, hash_api_key, redact_sensitive_dict,
    compute_entry_hash, authenticate_token
)
from app.rate_limiter import enforce_rate_limit, rate_limiter
from app.upstream_manager import upstream_manager
from app.meta_tools import META_TOOLS_DEFINITIONS, search_gateway_tools
from app.config import settings

logger = logging.getLogger("mcp-gateway-engine")
router = APIRouter(tags=["MCP Gateway Engine"])

# Restricted tools pattern for non-admin members
RESTRICTED_WRITE_PATTERNS = ["__create_product", "__update_order_status"]

async def check_tool_permission(role: str, qualified_tool_name: str, db: AsyncSession) -> bool:
    """Checks role permissions against DB policy table, falling back to role rules."""
    if role == UserRole.ADMIN.value:
        return True

    # Check DB policy table first
    stmt = select(ToolPermissionPolicy).where(ToolPermissionPolicy.role == role)
    policies = (await db.execute(stmt)).scalars().all()
    for p in policies:
        pattern = p.tool_pattern.replace("*", "")
        if pattern in qualified_tool_name:
            return p.allowed

    # Default rule: members cannot run store mutation tools
    for pattern in RESTRICTED_WRITE_PATTERNS:
        if qualified_tool_name.endswith(pattern):
            return False

    return True

import asyncio

_audit_lock = asyncio.Lock()

async def write_tamper_evident_audit_log(
    db: AsyncSession,
    auth: AuthContext,
    auth_method: str,
    server_slug: Optional[str],
    tool_name: Optional[str],
    arguments: Optional[Dict[str, Any]],
    duration_ms: float,
    outcome: str,
    error_message: Optional[str] = None
) -> AuditLog:
    """Persists a SHA-256 tamper-evident chained audit log with sequential hash linkage."""
    now = datetime.now(timezone.utc)
    redacted_args = redact_sensitive_dict(arguments) if arguments else None
    truncated_err = error_message[:1000] if error_message else None

    async with _audit_lock:
        # Get latest entry hash for chain linkage
        stmt = select(AuditLog.entry_hash).order_by(desc(AuditLog.id)).limit(1)
        res = await db.execute(stmt)
        prev_hash = res.scalar_one_or_none()

        entry_hash = compute_entry_hash(
            prev_hash=prev_hash,
            timestamp=now,
            user_id=auth.user_id,
            tool_name=tool_name,
            outcome=outcome
        )

        log = AuditLog(
            timestamp=now,
            user_id=auth.user_id,
            user_email=auth.user_email,
            user_role=auth.user_role,
            auth_method=auth_method,
            server_slug=server_slug,
            tool_name=tool_name,
            arguments_redacted=redacted_args,
            duration_ms=round(duration_ms, 2),
            outcome=outcome,
            error_message=truncated_err,
            prev_hash=prev_hash,
            entry_hash=entry_hash
        )
        db.add(log)
        await db.commit()
        return log

@router.get("/mcp/sse")
async def mcp_gateway_sse(request: Request, auth: AuthContext = Depends(get_current_auth)):
    """Standard Model Context Protocol (MCP) Server-Sent Events transport."""
    async def event_generator():
        yield {"event": "endpoint", "data": "/mcp"}
        yield {
            "event": "message",
            "data": json.dumps({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {"gateway": settings.PROJECT_NAME, "version": settings.VERSION}
            })
        }
    return EventSourceResponse(event_generator())

@router.post("/mcp")
async def mcp_gateway_jsonrpc(
    request: Request,
    x_mcp_scale_mode: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Unified High-Availability Streamable HTTP MCP Gateway Engine.
    Implements JSON-RPC 2.0 initialize, ping, tools/list, and tools/call.
    """
    start_time = time.monotonic()
    auth_header = request.headers.get("authorization", "")
    api_key_hdr = request.headers.get("x-api-key", "")

    # Parse Bearer Token
    raw_token = ""
    auth_method = "api_key"
    if auth_header.startswith("Bearer "):
        raw_token = auth_header[7:].strip()
    elif api_key_hdr:
        raw_token = api_key_hdr.strip()

    # 1. Instant Revocation & Authentication Check
    auth_context, auth_error = await authenticate_token(raw_token, db) if raw_token else (None, "INVALID")

    if auth_error == "REVOKED" and auth_context and auth_context.api_key:
        duration_ms = (time.monotonic() - start_time) * 1000
        await write_tamper_evident_audit_log(
            db=db,
            auth=auth_context,
            auth_method=auth_method,
            server_slug=None,
            tool_name=None,
            arguments=None,
            duration_ms=duration_ms,
            outcome=AuditOutcome.REJECTED_REVOKED_KEY.value,
            error_message=f"API key {auth_context.api_key.key_prefix}... was revoked at {auth_context.api_key.revoked_at.isoformat()}"
        )
        return JSONResponse(
            status_code=401,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": "API key has been revoked."}}
        )

    if not auth_context or not auth_context.is_authenticated:
        return JSONResponse(
            status_code=401,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": "Unauthorized: valid Bearer token or API key required."}}
        )

    # 2. Rate Limiting per API key / user
    rate_limit = settings.RATE_LIMIT_PER_KEY_PER_MIN
    if auth_context.api_key:
        client_id = f"key_{auth_context.api_key.id}"
    elif auth_context.user:
        client_id = f"user_{auth_context.user.id}"
    else:
        client_id = request.client.host if request.client else "unknown"

    allowed, _ = rate_limiter.check_rate_limit(client_id, rate_limit)
    if not allowed:
        duration_ms = (time.monotonic() - start_time) * 1000
        await write_tamper_evident_audit_log(
            db=db,
            auth=auth_context,
            auth_method=auth_method,
            server_slug=None,
            tool_name=None,
            arguments=None,
            duration_ms=duration_ms,
            outcome=AuditOutcome.RATE_LIMITED.value,
            error_message=f"Rate limit exceeded: max {rate_limit} requests/min"
        )
        return JSONResponse(
            status_code=429,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": "Rate limit exceeded."}}
        )

    # Parse JSON-RPC Payload
    try:
        body = await request.json()
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {str(exc)}"}}
        )

    rpc_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})

    # 3. Handshake & Ping
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": True},
                    "prompts": {},
                    "resources": {}
                },
                "serverInfo": {
                    "name": "urumi-mcp-gateway",
                    "version": settings.VERSION
                }
            }
        })

    elif method == "ping":
        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": "pong"})

    # 4. tools/list: Dynamic Fan-Out, Tool Collision Namespacing & Role Filtering
    elif method == "tools/list":
        # Check scale mode
        scale_mode = settings.SCALE_MODE_ENABLED or (x_mcp_scale_mode == "true") or request.query_params.get("scale_mode") == "true"

        if scale_mode:
            # Standout #4: Meta-Tool Search Mode
            duration_ms = (time.monotonic() - start_time) * 1000
            await write_tamper_evident_audit_log(
                db=db, auth=auth_context, auth_method=auth_method, server_slug=None,
                tool_name="tools/list[meta_mode]", arguments=None, duration_ms=duration_ms, outcome=AuditOutcome.SUCCESS.value
            )
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"tools": META_TOOLS_DEFINITIONS}
            })

        # Fetch active upstream servers
        stmt = select(UpstreamServer).where(UpstreamServer.enabled == True)
        res = await db.execute(stmt)
        servers = res.scalars().all()

        aggregated_tools = []
        user_role = auth_context.user_role

        for s in servers:
            for t in (s.cached_tools or []):
                orig_name = t.get("name")
                qualified_name = f"{s.slug}__{orig_name}"

                # Role-Based Tool Permissions: Filter out restricted write tools for members
                allowed = await check_tool_permission(user_role, qualified_name, db)
                if not allowed:
                    continue

                scoped_tool = dict(t)
                scoped_tool["name"] = qualified_name
                scoped_tool["description"] = f"[{s.name}] {t.get('description', '')}"
                aggregated_tools.append(scoped_tool)

        duration_ms = (time.monotonic() - start_time) * 1000
        await write_tamper_evident_audit_log(
            db=db, auth=auth_context, auth_method=auth_method, server_slug=None,
            tool_name="tools/list", arguments=None, duration_ms=duration_ms, outcome=AuditOutcome.SUCCESS.value
        )

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"tools": aggregated_tools}
        })

    # 5. tools/call: Dynamic Upstream Routing & Role Enforcement
    elif method == "tools/call":
        full_tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # Handle Meta-Tools directly
        if full_tool_name == "gateway__search_tools":
            q = arguments.get("query", "")
            limit = int(arguments.get("limit", 10))
            matches = await search_gateway_tools(q, limit, db)
            duration_ms = (time.monotonic() - start_time) * 1000
            await write_tamper_evident_audit_log(
                db=db, auth=auth_context, auth_method=auth_method, server_slug=None,
                tool_name=full_tool_name, arguments=arguments, duration_ms=duration_ms, outcome=AuditOutcome.SUCCESS.value
            )
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(matches, indent=2)}]}
            })

        elif full_tool_name == "gateway__execute_tool":
            target_name = arguments.get("tool_name", "")
            inner_args = arguments.get("arguments", {})
            full_tool_name = target_name
            arguments = inner_args

        # Enforce Role-Based Tool Permission
        has_perm = await check_tool_permission(auth_context.user_role, full_tool_name, db)
        if not has_perm:
            duration_ms = (time.monotonic() - start_time) * 1000
            err_msg = f"Forbidden: role '{auth_context.user_role}' does not have permission to execute '{full_tool_name}'."
            await write_tamper_evident_audit_log(
                db=db, auth=auth_context, auth_method=auth_method, server_slug=None,
                tool_name=full_tool_name, arguments=arguments, duration_ms=duration_ms,
                outcome=AuditOutcome.REJECTED_FORBIDDEN.value, error_message=err_msg
            )
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {err_msg}"}],
                    "isError": True
                }
            })

        # Resolve upstream server by slug
        if "__" not in full_tool_name:
            duration_ms = (time.monotonic() - start_time) * 1000
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32601, "message": f"Invalid tool format: '{full_tool_name}'. Must be 'slug__tool_name'."}
            })

        server_slug, target_tool = full_tool_name.split("__", 1)

        stmt = select(UpstreamServer).where(UpstreamServer.slug == server_slug)
        server = (await db.execute(stmt)).scalar_one_or_none()

        if not server:
            duration_ms = (time.monotonic() - start_time) * 1000
            await write_tamper_evident_audit_log(
                db=db, auth=auth_context, auth_method=auth_method, server_slug=server_slug,
                tool_name=target_tool, arguments=arguments, duration_ms=duration_ms,
                outcome=AuditOutcome.ERROR.value, error_message=f"Server '{server_slug}' not found"
            )
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32602, "message": f"Upstream server '{server_slug}' is not registered"}
            })

        if not server.enabled:
            duration_ms = (time.monotonic() - start_time) * 1000
            await write_tamper_evident_audit_log(
                db=db, auth=auth_context, auth_method=auth_method, server_slug=server_slug,
                tool_name=target_tool, arguments=arguments, duration_ms=duration_ms,
                outcome=AuditOutcome.REJECTED_DISABLED.value, error_message=f"Server '{server_slug}' is disabled"
            )
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32602, "message": f"Upstream server '{server_slug}' is currently disabled"}
            })

        # Execute on upstream server
        try:
            call_res = await upstream_manager.execute_tool_call(server, target_tool, arguments)
            duration_ms = call_res.get("latency_ms", (time.monotonic() - start_time) * 1000)
            await db.commit()

            await write_tamper_evident_audit_log(
                db=db, auth=auth_context, auth_method=auth_method, server_slug=server_slug,
                tool_name=target_tool, arguments=arguments, duration_ms=duration_ms,
                outcome=AuditOutcome.SUCCESS.value
            )

            return JSONResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": call_res.get("result", {})
            })

        except TimeoutError as te:
            duration_ms = (time.monotonic() - start_time) * 1000
            await write_tamper_evident_audit_log(
                db=db, auth=auth_context, auth_method=auth_method, server_slug=server_slug,
                tool_name=target_tool, arguments=arguments, duration_ms=duration_ms,
                outcome=AuditOutcome.TIMEOUT.value, error_message=str(te)
            )
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "content": [{"type": "text", "text": f"Timeout: {str(te)}"}],
                    "isError": True
                }
            })

        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            await write_tamper_evident_audit_log(
                db=db, auth=auth_context, auth_method=auth_method, server_slug=server_slug,
                tool_name=target_tool, arguments=arguments, duration_ms=duration_ms,
                outcome=AuditOutcome.ERROR.value, error_message=str(exc)
            )
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "content": [{"type": "text", "text": f"Execution error: {str(exc)}"}],
                    "isError": True
                }
            })

    else:
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": f"Method '{method}' is not supported by MCP Gateway"}
        })
