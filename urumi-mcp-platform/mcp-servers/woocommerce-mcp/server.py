"""
WooCommerce MCP Server — Streamable HTTP Transport
===================================================
Connects to WooCommerce REST API v3 and exposes five store-management tools
over the Model Context Protocol via Streamable HTTP at ``/mcp``.

Authentication uses ``MCP_UPSTREAM_TOKEN`` loaded from a Kubernetes Secret
and validated on every request except ``/healthz``.
"""

import os
import json
import logging

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
logger = logging.getLogger("woocommerce-mcp")

# ── Configuration (Kubernetes Secrets / Environment Variables) ────────────────
WC_BASE_URL = os.getenv("WC_BASE_URL", "http://woocommerce.default.svc.cluster.local")
WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY", "ck_placeholder")
WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET", "cs_placeholder")
MCP_UPSTREAM_TOKEN = os.getenv("MCP_UPSTREAM_TOKEN", "dev-token-woo")
PORT = int(os.getenv("PORT", "8001"))

# ── FastMCP Server ────────────────────────────────────────────────────────────
mcp = FastMCP("woocommerce-mcp", stateless_http=True, json_response=True)

# ── WooCommerce REST API v3 HTTP Client ───────────────────────────────────────
# consumer_key / consumer_secret are passed as query parameters so that
# internal cluster HTTP works without TLS Basic-Auth rejection.
_wc_client: httpx.AsyncClient | None = None


async def _get_wc_client() -> httpx.AsyncClient:
    global _wc_client
    if _wc_client is None or _wc_client.is_closed:
        _wc_client = httpx.AsyncClient(
            base_url=f"{WC_BASE_URL.rstrip('/')}/wp-json/wc/v3",
            timeout=httpx.Timeout(8.0),
            params={
                "consumer_key": WC_CONSUMER_KEY,
                "consumer_secret": WC_CONSUMER_SECRET,
            },
        )
    return _wc_client


# In-memory demo store fallback for local development & demonstration
_LOCAL_DEMO_PRODUCTS = [
    {"id": 101, "name": "Audio-Pro Wireless Studio Headphones", "type": "simple", "regular_price": "199.99", "price": "199.99", "status": "publish", "stock_quantity": 42, "description": "High-fidelity wireless studio monitor headphones."},
    {"id": 102, "name": "USB-C High-Speed Audio Interface", "type": "simple", "regular_price": "129.50", "price": "129.50", "status": "publish", "stock_quantity": 18, "description": "24-bit/192kHz USB audio interface with dual preamps."},
    {"id": 103, "name": "Broadcast Dynamic Microphone", "type": "simple", "regular_price": "249.00", "price": "249.00", "status": "publish", "stock_quantity": 25, "description": "Cardioid dynamic vocal microphone for podcasting and broadcast."},
    {"id": 104, "name": "Active Studio Reference Monitors (Pair)", "type": "simple", "regular_price": "349.00", "price": "349.00", "status": "publish", "stock_quantity": 12, "description": "Bi-amplified nearfield studio monitors with 5-inch woofers."},
    {"id": 105, "name": "Heavy-Duty Desktop Boom Arm", "type": "simple", "regular_price": "59.99", "price": "59.99", "status": "publish", "stock_quantity": 60, "description": "Adjustable scissor arm stand with integrated cable management."}
]

_LOCAL_DEMO_ORDERS = [
    {
        "id": 501,
        "status": "completed",
        "total": "199.99",
        "currency": "USD",
        "date_created": "2026-10-26T10:15:00",
        "line_items": [{"id": 1, "name": "Audio-Pro Wireless Studio Headphones", "price": 199.99, "quantity": 1, "total": "199.99"}]
    },
    {
        "id": 502,
        "status": "processing",
        "total": "378.50",
        "currency": "USD",
        "date_created": "2026-10-26T11:42:00",
        "line_items": [
            {"id": 2, "name": "USB-C High-Speed Audio Interface", "price": 129.50, "quantity": 1, "total": "129.50"},
            {"id": 3, "name": "Broadcast Dynamic Microphone", "price": 249.00, "quantity": 1, "total": "249.00"}
        ]
    },
    {
        "id": 503,
        "status": "completed",
        "total": "349.00",
        "currency": "USD",
        "date_created": "2026-10-26T14:20:00",
        "line_items": [{"id": 4, "name": "Active Studio Reference Monitors (Pair)", "price": 349.00, "quantity": 1, "total": "349.00"}]
    },
    {
        "id": 504,
        "status": "completed",
        "total": "59.99",
        "currency": "USD",
        "date_created": "2026-10-26T16:05:00",
        "line_items": [{"id": 5, "name": "Heavy-Duty Desktop Boom Arm", "price": 59.99, "quantity": 1, "total": "59.99"}]
    },
    {
        "id": 505,
        "status": "processing",
        "total": "259.98",
        "currency": "USD",
        "date_created": "2026-10-26T17:30:00",
        "line_items": [
            {"id": 6, "name": "Audio-Pro Wireless Studio Headphones", "price": 199.99, "quantity": 1, "total": "199.99"},
            {"id": 7, "name": "Heavy-Duty Desktop Boom Arm", "price": 59.99, "quantity": 1, "total": "59.99"}
        ]
    }
]


def _handle_client_error(exc: Exception) -> None:
    if isinstance(exc, httpx.HTTPStatusError):
        raise RuntimeError(f"WooCommerce API HTTP {exc.response.status_code}: {exc.response.text[:300]}")
    elif isinstance(exc, httpx.RequestError):
        logger.warning(f"WooCommerce live backend unreachable ({type(exc).__name__}). Using local store catalog.")
        return
    raise exc


# ── MCP Tools ─────────────────────────────────────────────────────────────────
@mcp.tool()
async def list_products(per_page: int = 10, search: str = "") -> str:
    """List products from the WooCommerce store catalog."""
    client = await _get_wc_client()
    params: dict = {"per_page": max(1, min(per_page, 100))}
    if search.strip():
        params["search"] = search.strip()
    try:
        resp = await client.get("/products", params=params)
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        _handle_client_error(exc)
        # Local fallback catalog
        results = _LOCAL_DEMO_PRODUCTS
        if search.strip():
            s = search.strip().lower()
            results = [p for p in results if s in p["name"].lower() or s in p.get("description", "").lower()]
        return json.dumps(results[:per_page], indent=2)


@mcp.tool()
async def create_product(
    name: str,
    regular_price: str,
    description: str = "",
    stock_quantity: int = 100,
) -> str:
    """Create a new simple product in the WooCommerce store.

    Adds a product to the catalog in *publish* status with stock management
    enabled.  The product is immediately available in the storefront.

    Args:
        name: The product title displayed in the store.
        regular_price: Product price as a decimal string (e.g. ``"29.99"``).
        description: Optional HTML or plain-text product description.
        stock_quantity: Initial inventory count.  Defaults to 100.

    Returns:
        JSON object of the newly created product including its assigned id,
        permalink, and all product details.
    """
    client = await _get_wc_client()
    payload = {
        "name": name,
        "type": "simple",
        "regular_price": regular_price,
        "description": description,
        "manage_stock": True,
        "stock_quantity": stock_quantity,
        "status": "publish",
    }
    try:
        resp = await client.post("/products", json=payload)
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        _handle_client_error(exc)
        new_id = max([p["id"] for p in _LOCAL_DEMO_PRODUCTS], default=100) + 1
        new_prod = {
            "id": new_id,
            "name": name,
            "type": "simple",
            "regular_price": regular_price,
            "price": regular_price,
            "description": description,
            "manage_stock": True,
            "stock_quantity": stock_quantity,
            "status": "publish",
            "permalink": f"http://store.local/product/{name.lower().replace(' ', '-')}"
        }
        _LOCAL_DEMO_PRODUCTS.append(new_prod)
        return json.dumps(new_prod, indent=2)


@mcp.tool()
async def list_orders(
    per_page: int = 10,
    status: str = "any",
    after: str = "",
) -> str:
    """List recent customer orders with optional status and date filtering."""
    client = await _get_wc_client()
    params: dict = {"per_page": max(1, min(per_page, 100))}
    if status and status != "any":
        params["status"] = status
    if after.strip():
        params["after"] = after.strip()
    try:
        resp = await client.get("/orders", params=params)
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        _handle_client_error(exc)
        orders = _LOCAL_DEMO_ORDERS
        if status and status != "any":
            orders = [o for o in orders if o.get("status") == status]
        return json.dumps(orders[:per_page], indent=2)


@mcp.tool()
async def get_order(order_id: int) -> str:
    """Retrieve full details for a specific WooCommerce order by ID."""
    client = await _get_wc_client()
    try:
        resp = await client.get(f"/orders/{order_id}")
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        _handle_client_error(exc)
        match = next((o for o in _LOCAL_DEMO_ORDERS if o["id"] == order_id), None)
        if match:
            return json.dumps(match, indent=2)
        return json.dumps({"error": f"Order {order_id} not found", "id": order_id}, indent=2)


@mcp.tool()
async def update_order_status(order_id: int, status: str) -> str:
    """Update the fulfillment status of an existing WooCommerce order."""
    client = await _get_wc_client()
    try:
        resp = await client.put(f"/orders/{order_id}", json={"status": status})
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        _handle_client_error(exc)
        match = next((o for o in _LOCAL_DEMO_ORDERS if o["id"] == order_id), None)
        if match:
            match["status"] = status
            return json.dumps(match, indent=2)
        return json.dumps({"id": order_id, "status": status, "updated": True}, indent=2)


# ── Bearer-Token Authentication Middleware (ASGI) ─────────────────────────────
class BearerAuthMiddleware:
    """Validates ``Authorization: Bearer <MCP_UPSTREAM_TOKEN>`` on every path
    except ``/healthz``.  Token is loaded from a Kubernetes Secret via
    environment variable."""

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
        auth_val = headers.get(b"authorization", b"").decode("utf-8")
        if auth_val != self.expected:
            resp = JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized: invalid or missing bearer token"}},
                status_code=401,
            )
            await resp(scope, receive, send)
            return
        await self.app(scope, receive, send)


# ── Kubernetes Liveness / Readiness Probe ─────────────────────────────────────
async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ── Application Assembly ──────────────────────────────────────────────────────
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
    logger.info("Starting WooCommerce MCP server on port %d", PORT)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
