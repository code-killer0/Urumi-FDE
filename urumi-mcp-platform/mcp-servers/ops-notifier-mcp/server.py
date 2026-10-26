"""
Ops & Notifier MCP Server — Streamable HTTP Transport
=====================================================
Handles operational alert dispatch (Slack / webhook), alert history,
and fulfillment-ticket creation for warehouse teams.  Stores state in
memory for stateless pod compatibility.
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
from starlette.requests import Request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ops-notifier-mcp")

MCP_UPSTREAM_TOKEN = os.getenv("MCP_UPSTREAM_TOKEN", "dev-token-ops")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", "8003"))

mcp = FastMCP("ops-notifier-mcp", stateless_http=True, json_response=True)

# ── In-Memory Stores ─────────────────────────────────────────────────────────
_alerts_store: list[dict] = []
_tickets_store: list[dict] = []


# ── MCP Tools ─────────────────────────────────────────────────────────────────
@mcp.tool()
async def send_order_summary_alert(
    channel: str,
    summary_text: str,
    order_count: int,
    total_revenue: float,
) -> str:
    """Dispatch an order-summary notification to a Slack channel or webhook.

    Sends a formatted operational alert containing order volume and revenue
    totals.  The alert is stored in the internal dispatch log and, if
    ``SLACK_WEBHOOK_URL`` is configured, simultaneously posted to Slack.
    Returns a unique receipt ID for tracking and audit correlation.

    Args:
        channel: Target notification channel (e.g. ``#ops-alerts``).
        summary_text: Human-readable summary message body.
        order_count: Number of orders covered in this summary period.
        total_revenue: Aggregate revenue amount for the period.

    Returns:
        JSON with receipt_id, channel, dispatched_at, status, and the
        original summary details.
    """
    receipt_id = f"alert-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    record: dict = {
        "receipt_id": receipt_id,
        "channel": channel,
        "summary_text": summary_text,
        "order_count": order_count,
        "total_revenue": round(total_revenue, 2),
        "dispatched_at": now.isoformat(),
        "status": "dispatched",
    }
    _alerts_store.append(record)
    logger.info("Alert dispatched: %s → %s", receipt_id, channel)

    if SLACK_WEBHOOK_URL:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(SLACK_WEBHOOK_URL, json={
                    "channel": channel,
                    "text": (
                        f":bar_chart: *Order Summary Alert*\n{summary_text}\n"
                        f"Orders: {order_count} | Revenue: ${total_revenue:,.2f}\n"
                        f"Receipt: `{receipt_id}`"
                    ),
                })
                record["status"] = "delivered_slack"
        except Exception as exc:
            record["status"] = "dispatched_slack_failed"
            record["slack_error"] = str(exc)[:200]

    return json.dumps(record, indent=2)


@mcp.tool()
async def list_dispatched_alerts(limit: int = 10) -> str:
    """Retrieve the most recently dispatched operational alerts.

    Returns a reverse-chronological list of alert records from the dispatch
    log, including receipt IDs, channels, timestamps, and delivery status.
    Useful for auditing notification history and verifying delivery.

    Args:
        limit: Maximum number of alerts to return (1-100, default 10).

    Returns:
        JSON with total_count, returned_count, and alerts array.
    """
    capped = max(1, min(limit, 100))
    recent = list(reversed(_alerts_store))[:capped]
    return json.dumps({
        "total_count": len(_alerts_store),
        "returned_count": len(recent),
        "alerts": recent,
    }, indent=2)


@mcp.tool()
async def create_fulfillment_ticket(
    order_id: int,
    priority: str,
    notes: str,
) -> str:
    """Create an internal fulfillment tracking ticket for an order.

    Generates a structured ticket for warehouse or operations teams to
    track order fulfillment progress.  Tickets are assigned a unique ID,
    priority level, and routed to the appropriate fulfillment queue.

    Args:
        order_id: WooCommerce order ID this ticket is associated with.
        priority: Ticket priority — ``low``, ``normal``, ``high``, or ``urgent``.
        notes: Free-text special-handling instructions for the team.

    Returns:
        JSON with ticket_id, order_id, priority, status, notes,
        assigned_queue, and created_at.
    """
    valid = {"low", "normal", "high", "urgent"}
    if priority.lower() not in valid:
        return json.dumps({"error": f"Invalid priority '{priority}'. Must be one of: {sorted(valid)}"})

    ticket_id = f"FT-{uuid.uuid4().hex[:8].upper()}"
    queue_map = {
        "urgent": "express-fulfillment",
        "high": "priority-fulfillment",
        "normal": "standard-fulfillment",
        "low": "batch-fulfillment",
    }

    ticket: dict = {
        "ticket_id": ticket_id,
        "order_id": order_id,
        "priority": priority.lower(),
        "status": "open",
        "notes": notes,
        "assigned_queue": queue_map[priority.lower()],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _tickets_store.append(ticket)
    logger.info("Fulfillment ticket %s created for order %d", ticket_id, order_id)
    return json.dumps(ticket, indent=2)


# ── Bearer Auth Middleware ────────────────────────────────────────────────────
class BearerAuthMiddleware:
    def __init__(self, app, *, token: str):
        self.app = app
        self.expected = f"Bearer {token}"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path", "") == "/healthz":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        if headers.get(b"authorization", b"").decode() != self.expected:
            resp = JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized"}},
                status_code=401,
            )
            await resp(scope, receive, send)
            return
        await self.app(scope, receive, send)


async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app() -> Starlette:
    mcp_http = mcp.streamable_http_app()
    app = Starlette(
        lifespan=mcp_http.router.lifespan_context,
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Mount("/", app=mcp_http),
        ],
    )
    app.add_middleware(BearerAuthMiddleware, token=MCP_UPSTREAM_TOKEN)
    return app


app = create_app()

if __name__ == "__main__":
    logger.info("Starting Ops & Notifier MCP server on port %d", PORT)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
