import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.config import settings
from app.database import engine, Base, AsyncSessionLocal
from app.models import (
    User, UserRole, UpstreamServer, ServerStatus, ToolPermissionPolicy,
    ApiKey
)
from app.security import get_password_hash, encrypt_credential, generate_api_key_pair
from app.upstream_manager import upstream_manager
from app.routers import auth, servers, keys, audit, chat, stores
from app.k8s_provisioner import k8s_provisioner
from app.mcp_gateway import router as mcp_gateway_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("urumi-gateway-main")

async def seed_initial_data():
    """Seeds default accounts, upstream servers, and role permission policies."""
    async with AsyncSessionLocal() as session:
        # 1. Seed User A (Admin)
        admin_stmt = select(User).where(User.email == settings.ADMIN_EMAIL)
        admin_user = (await session.execute(admin_stmt)).scalar_one_or_none()
        if not admin_user:
            logger.info(f"Seeding default admin user: {settings.ADMIN_EMAIL}")
            admin_user = User(
                email=settings.ADMIN_EMAIL,
                name="System Administrator",
                password_hash=get_password_hash(settings.ADMIN_PASSWORD),
                role=UserRole.ADMIN.value
            )
            session.add(admin_user)
            await session.commit()
            await session.refresh(admin_user)

        # 2. Seed User B (Member)
        member_stmt = select(User).where(User.email == settings.MEMBER_EMAIL)
        member_user = (await session.execute(member_stmt)).scalar_one_or_none()
        if not member_user:
            logger.info(f"Seeding default member user: {settings.MEMBER_EMAIL}")
            member_user = User(
                email=settings.MEMBER_EMAIL,
                name="Operations Member",
                password_hash=get_password_hash(settings.MEMBER_PASSWORD),
                role=UserRole.MEMBER.value
            )
            session.add(member_user)
            await session.commit()

        # 3. Seed Default Upstream MCP Servers (woo, promos, ops)
        default_servers = [
            {
                "name": "WooCommerce Store Operations",
                "slug": "woo",
                "url": settings.WOO_MCP_URL,
                "token": settings.WOO_MCP_TOKEN
            },
            {
                "name": "Promotions & Analytics",
                "slug": "promos",
                "url": settings.PROMOS_MCP_URL,
                "token": settings.PROMOS_MCP_TOKEN
            },
            {
                "name": "Operations & Notifier",
                "slug": "ops",
                "url": settings.OPS_MCP_URL,
                "token": settings.OPS_MCP_TOKEN
            }
        ]

        for s_data in default_servers:
            srv_stmt = select(UpstreamServer).where(UpstreamServer.slug == s_data["slug"])
            existing_srv = (await session.execute(srv_stmt)).scalar_one_or_none()
            if not existing_srv:
                logger.info(f"Seeding upstream MCP server: {s_data['slug']} ({s_data['url']})")
                new_srv = UpstreamServer(
                    name=s_data["name"],
                    slug=s_data["slug"],
                    url=s_data["url"],
                    auth_header_name="Authorization",
                    encrypted_credential=encrypt_credential(s_data["token"]),
                    enabled=True,
                    is_hosted=False,
                    status=ServerStatus.CONNECTED.value,
                    cached_tools=[]
                )
                session.add(new_srv)
                await session.commit()

        # 4. Seed Default Tool Permission Policies for Member Role
        pol_stmt = select(ToolPermissionPolicy).where(ToolPermissionPolicy.role == UserRole.MEMBER.value)
        policies = (await session.execute(pol_stmt)).scalars().all()
        if not policies:
            default_policies = [
                ToolPermissionPolicy(role=UserRole.MEMBER.value, tool_pattern="*__create_product", allowed=False),
                ToolPermissionPolicy(role=UserRole.MEMBER.value, tool_pattern="*__update_order_status", allowed=False),
                ToolPermissionPolicy(role=UserRole.MEMBER.value, tool_pattern="*__list_products", allowed=True),
                ToolPermissionPolicy(role=UserRole.MEMBER.value, tool_pattern="*__list_orders", allowed=True),
                ToolPermissionPolicy(role=UserRole.MEMBER.value, tool_pattern="*__get_order", allowed=True),
                ToolPermissionPolicy(role=UserRole.MEMBER.value, tool_pattern="*__calculate_order_metrics", allowed=True),
                ToolPermissionPolicy(role=UserRole.MEMBER.value, tool_pattern="*__recommend_discount_tier", allowed=True),
                ToolPermissionPolicy(role=UserRole.MEMBER.value, tool_pattern="*__convert_store_currency", allowed=True),
                ToolPermissionPolicy(role=UserRole.MEMBER.value, tool_pattern="*__send_order_summary_alert", allowed=True),
                ToolPermissionPolicy(role=UserRole.MEMBER.value, tool_pattern="*__list_dispatched_alerts", allowed=True),
                ToolPermissionPolicy(role=UserRole.MEMBER.value, tool_pattern="*__create_fulfillment_ticket", allowed=True),
            ]
            session.add_all(default_policies)
            await session.commit()

        # 5. Seed default demo API Key for Admin
        key_stmt = select(ApiKey).where(ApiKey.name == "admin-default-demo-key")
        existing_key = (await session.execute(key_stmt)).scalar_one_or_none()
        if not existing_key:
            raw_k, pref, kh = generate_api_key_pair()
            # Deterministic demo key for quick local CLI / cURL verification
            demo_raw_key = "urumi_sk_0000000000000000000000000000demo"
            demo_pref = demo_raw_key[:12]
            from app.security import hash_api_key
            demo_kh = hash_api_key(demo_raw_key)

            demo_key = ApiKey(
                user_id=admin_user.id,
                name="admin-default-demo-key",
                key_prefix=demo_pref,
                key_hash=demo_kh,
                revoked_at=None
            )
            session.add(demo_key)
            await session.commit()
            logger.info(f"Default admin demo API key created: {demo_raw_key}")

async def background_health_checker():
    """Periodic health-check loop every 5s probing upstream servers and syncing cached tools."""
    while True:
        try:
            await asyncio.sleep(settings.HEALTH_CHECK_INTERVAL_SECONDS)
            async with AsyncSessionLocal() as session:
                stmt = select(UpstreamServer).where(UpstreamServer.enabled == True)
                servers_list = (await session.execute(stmt)).scalars().all()
                for s in servers_list:
                    await upstream_manager.probe_and_sync_server(s, session)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in background health check loop: {e}")

async def background_store_reconciler():
    """Periodic reconciliation loop every 15s reconciling ProvisionedStore state."""
    while True:
        try:
            await asyncio.sleep(settings.RECONCILIATION_INTERVAL_SECONDS)
            async with AsyncSessionLocal() as session:
                await k8s_provisioner.reconcile_provisioning_stores(session)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in store reconciliation loop: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Urumi MCP Gateway tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await seed_initial_data()

    # Initial live probe
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(UpstreamServer).where(UpstreamServer.enabled == True)
            servers_list = (await session.execute(stmt)).scalars().all()
            for s in servers_list:
                await upstream_manager.probe_and_sync_server(s, session)
            # Initial store reconciliation
            await k8s_provisioner.reconcile_provisioning_stores(session)
    except Exception as e:
        logger.warning(f"Initial upstream server probe note: {e}")

    health_task = asyncio.create_task(background_health_checker())
    reconcile_task = asyncio.create_task(background_store_reconciler())
    yield
    health_task.cancel()
    reconcile_task.cancel()
    if upstream_manager.http_client and not upstream_manager.http_client.is_closed:
        await upstream_manager.http_client.aclose()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="High-Availability Model Context Protocol (MCP) Gateway Engine for WooCommerce Hosting.",
    lifespan=lifespan
)

# CORS Middleware — explicit origins instead of wildcard to safely allow credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",        # Vite dev server
        "http://localhost:3000",        # Alternate dev port
        "http://app.127.0.0.1.nip.io", # Local K8s dashboard
        "https://app.127.0.0.1.nip.io",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Kubernetes Liveness / Readiness Probe
@app.get("/healthz", tags=["Health"])
async def healthz():
    return {"status": "ok"}

# Mount MCP Gateway Engine (/mcp and /mcp/sse)
app.include_router(mcp_gateway_router)

# Mount REST API v1
api_v1 = FastAPI(title="Urumi Gateway API v1")
api_v1.include_router(auth.router)
api_v1.include_router(servers.router)
api_v1.include_router(keys.router)
api_v1.include_router(audit.router)
api_v1.include_router(chat.router)
api_v1.include_router(stores.router)
app.mount("/api/v1", api_v1)

# Mount /api as an alias to /api/v1 for convenience (e.g. POST /api/chat)
# Uses a single sub-app to avoid duplicate router registrations
api_alias = FastAPI(title="Urumi Gateway API")
api_alias.include_router(auth.router)
api_alias.include_router(servers.router)
api_alias.include_router(keys.router)
api_alias.include_router(audit.router)
api_alias.include_router(chat.router)
api_alias.include_router(stores.router)
app.mount("/api", api_alias)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
