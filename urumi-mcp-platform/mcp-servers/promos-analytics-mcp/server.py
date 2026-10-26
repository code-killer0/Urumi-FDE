"""
Promotions & Analytics MCP Server — Streamable HTTP Transport
=============================================================
Pure-compute analytics engine for order metrics, discount-tier
recommendations, and multi-currency conversion.  No external database
required — all logic is self-contained.
"""

import os
import json
import logging
from datetime import datetime, timezone

import httpx  # available for future live FX-rate API calls
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
logger = logging.getLogger("promos-analytics-mcp")

MCP_UPSTREAM_TOKEN = os.getenv("MCP_UPSTREAM_TOKEN", "dev-token-promos")
PORT = int(os.getenv("PORT", "8002"))

mcp = FastMCP("promos-analytics-mcp", stateless_http=True, json_response=True)

# ── Static Exchange Rates (production → live API via httpx) ───────────────────
EXCHANGE_RATES: dict[str, float] = {
    "USD": 1.0, "EUR": 0.92, "GBP": 0.79, "INR": 83.42,
    "JPY": 149.50, "CAD": 1.36, "AUD": 1.53, "SGD": 1.34,
}

# ── Discount Tier Engine ──────────────────────────────────────────────────────
DISCOUNT_TIERS = [
    {"min_total": 500, "min_orders": 10, "code": "VIP20",     "pct": 20, "tier": "VIP"},
    {"min_total": 200, "min_orders":  5, "code": "LOYAL15",   "pct": 15, "tier": "Loyal"},
    {"min_total": 100, "min_orders":  3, "code": "REPEAT10",  "pct": 10, "tier": "Repeat"},
    {"min_total":  50, "min_orders":  1, "code": "WELCOME5",  "pct":  5, "tier": "Welcome"},
    {"min_total":   0, "min_orders":  0, "code": "NEWUSER3",  "pct":  3, "tier": "New User"},
]


# ── MCP Tools ─────────────────────────────────────────────────────────────────
@mcp.tool()
async def calculate_order_metrics(
    order_totals: list[float],
    currency: str = "USD",
) -> str:
    """Calculate aggregate revenue analytics from a batch of order totals.

    Computes total revenue, average order value (AOV), min/max orders, and
    a projected 30-day revenue run-rate based on the provided sample.
    Useful for executive dashboards and financial planning.

    Args:
        order_totals: List of numeric order total amounts
                      (e.g. ``[29.99, 149.50, 75.00]``).
        currency: ISO 4217 currency code for the amounts.  Defaults to ``USD``.

    Returns:
        JSON object with total_revenue, order_count, average_order_value,
        min_order, max_order, projected_30_day_revenue, and currency.
    """
    if not order_totals:
        return json.dumps({"error": "order_totals list must not be empty"})

    total = sum(order_totals)
    count = len(order_totals)
    avg = total / count
    projected_30 = total * 30  # assumes sample = 1 day

    return json.dumps({
        "total_revenue": round(total, 2),
        "order_count": count,
        "average_order_value": round(avg, 2),
        "min_order": round(min(order_totals), 2),
        "max_order": round(max(order_totals), 2),
        "projected_30_day_revenue": round(projected_30, 2),
        "currency": currency,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2)


@mcp.tool()
async def recommend_discount_tier(
    order_total: float,
    customer_order_count: int = 1,
) -> str:
    """Recommend a promotional discount tier based on customer behaviour.

    Analyses the customer's current cart total and historical purchase count
    to select the optimal coupon.  Returns coupon code, discount percentage,
    estimated margin impact, and tier classification.

    Args:
        order_total: The customer's current cart or order total.
        customer_order_count: Number of completed orders by this customer.

    Returns:
        JSON with tier, coupon_code, discount_percent, discount_amount,
        net_total_after_discount, and margin_impact_percent.
    """
    selected = DISCOUNT_TIERS[-1]  # fallback
    for tier in DISCOUNT_TIERS:
        if order_total >= tier["min_total"] and customer_order_count >= tier["min_orders"]:
            selected = tier
            break

    disc_amt = round(order_total * selected["pct"] / 100, 2)
    net = round(order_total - disc_amt, 2)

    return json.dumps({
        "tier": selected["tier"],
        "coupon_code": selected["code"],
        "discount_percent": selected["pct"],
        "discount_amount": disc_amt,
        "original_total": order_total,
        "net_total_after_discount": net,
        "margin_impact_percent": round(-selected["pct"] * 0.6, 2),
        "recommendation_rationale": (
            f"Customer has {customer_order_count} order(s) totalling "
            f"${order_total:.2f}, qualifying for {selected['tier']} tier."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2)


@mcp.tool()
async def convert_store_currency(
    amount: float,
    from_currency: str = "USD",
    to_currency: str = "INR",
) -> str:
    """Convert an amount between store-supported currencies.

    Performs currency conversion using embedded exchange rates pivoted
    through USD.  Supports USD, EUR, GBP, INR, JPY, CAD, AUD, SGD.

    Args:
        amount: Numeric amount to convert.
        from_currency: Source ISO 4217 currency code (default ``USD``).
        to_currency: Target ISO 4217 currency code (default ``INR``).

    Returns:
        JSON with original_amount, from_currency, to_currency,
        converted_amount, exchange_rate, and timestamp.
    """
    src = from_currency.upper()
    dst = to_currency.upper()

    if src not in EXCHANGE_RATES:
        return json.dumps({"error": f"Unsupported source currency: {src}", "supported": list(EXCHANGE_RATES)})
    if dst not in EXCHANGE_RATES:
        return json.dumps({"error": f"Unsupported target currency: {dst}", "supported": list(EXCHANGE_RATES)})

    usd = amount / EXCHANGE_RATES[src]
    converted = usd * EXCHANGE_RATES[dst]
    rate = EXCHANGE_RATES[dst] / EXCHANGE_RATES[src]

    return json.dumps({
        "original_amount": amount,
        "from_currency": src,
        "to_currency": dst,
        "converted_amount": round(converted, 2),
        "exchange_rate": round(rate, 6),
        "rate_source": "embedded_static",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, indent=2)


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
    logger.info("Starting Promos & Analytics MCP server on port %d", PORT)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
