import asyncio
from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import ProvisionedStore, StoreStatus, UpstreamServer, ServerStatus, UserRole
from app.schemas import ProvisionedStoreCreate, ProvisionedStoreResponse
from app.security import require_auth, AuthContext, encrypt_credential
from app.k8s_provisioner import k8s_provisioner
from app.config import settings

router = APIRouter(prefix="/stores", tags=["Multi-Store Kubernetes Provisioning"])

@router.get("", response_model=List[ProvisionedStoreResponse])
async def list_stores(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_auth)
):
    if auth.is_admin:
        stmt = select(ProvisionedStore).order_by(ProvisionedStore.id.desc())
    else:
        stmt = select(ProvisionedStore).where(ProvisionedStore.owner_user_id == auth.user_id).order_by(ProvisionedStore.id.desc())
    res = await db.execute(stmt)
    stores = res.scalars().all()

    # Enrich with mcp_server_slug
    out = []
    for s in stores:
        resp_item = ProvisionedStoreResponse(
            id=s.id,
            name=s.name,
            slug=s.slug,
            namespace=s.namespace,
            owner_user_id=s.owner_user_id,
            status=s.status,
            store_url=s.store_url,
            mcp_server_id=s.mcp_server_id,
            mcp_server_slug=f"store_{s.slug}",
            error_reason=s.error_reason,
            created_at=s.created_at,
            updated_at=s.updated_at
        )
        out.append(resp_item)
    return out

@router.post("", response_model=ProvisionedStoreResponse, status_code=status.HTTP_201_CREATED)
async def create_store(
    store_in: ProvisionedStoreCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_auth)
):
    """
    Provisions a new isolated WooCommerce store tenant in a dedicated Kubernetes namespace.
    Enforces per-user store quotas and registers its dedicated woocommerce-mcp pod in the Gateway.
    """
    if not auth.user:
        raise HTTPException(status_code=400, detail="User login session required.")

    # 1. Enforce MAX_STORES_PER_USER quota
    count_stmt = select(func.count(ProvisionedStore.id)).where(ProvisionedStore.owner_user_id == auth.user_id)
    existing_count = (await db.execute(count_stmt)).scalar() or 0
    if existing_count >= settings.MAX_STORES_PER_USER and not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Store quota exceeded. Maximum {settings.MAX_STORES_PER_USER} stores allowed per user."
        )

    # 2. Check slug uniqueness
    slug_stmt = select(ProvisionedStore).where(ProvisionedStore.slug == store_in.slug)
    existing_slug = (await db.execute(slug_stmt)).scalar_one_or_none()
    if existing_slug:
        raise HTTPException(status_code=400, detail=f"Store slug '{store_in.slug}' is already taken.")

    now = datetime.now(timezone.utc)
    ns_name = f"{settings.K8S_NAMESPACE_PREFIX}{store_in.slug}"

    # 3. Create initial ProvisionedStore row in "Provisioning" state
    new_store = ProvisionedStore(
        name=store_in.name,
        slug=store_in.slug,
        namespace=ns_name,
        owner_user_id=auth.user_id,
        status=StoreStatus.PROVISIONING.value,
        store_url=f"http://store-{store_in.slug}.{settings.GATEWAY_INGRESS_DOMAIN}",
        created_at=now,
        updated_at=now
    )
    db.add(new_store)
    await db.commit()
    await db.refresh(new_store)

    try:
        # 4. Trigger Kubernetes / Helm provisioning
        prov_res = await k8s_provisioner.provision_store(store_in.slug, auth.user_id, db)

        # 5. Automatically register dedicated UpstreamServer in Gateway
        upstream_slug = f"store_{store_in.slug}"
        upstream_srv = UpstreamServer(
            name=f"WooCommerce — {store_in.name}",
            slug=upstream_slug,
            url=prov_res["mcp_url"],
            auth_header_name="Authorization",
            encrypted_credential=encrypt_credential(prov_res["mcp_token"]),
            enabled=True,
            is_hosted=True,
            store_id=new_store.id,
            status=ServerStatus.CONNECTED.value,
            # Pre-cache standard WooCommerce MCP tools
            cached_tools=[
                {"name": "list_products", "description": f"List products from {store_in.name} catalog", "inputSchema": {"type": "object"}},
                {"name": "create_product", "description": f"Create new product in {store_in.name}", "inputSchema": {"type": "object"}},
                {"name": "list_orders", "description": f"List orders from {store_in.name}", "inputSchema": {"type": "object"}},
                {"name": "get_order", "description": f"Get order details from {store_in.name}", "inputSchema": {"type": "object"}},
                {"name": "update_order_status", "description": f"Update order status in {store_in.name}", "inputSchema": {"type": "object"}},
            ],
            created_at=now
        )
        db.add(upstream_srv)
        await db.commit()
        await db.refresh(upstream_srv)

        # 6. Update Store to Ready
        new_store.status = StoreStatus.READY.value
        new_store.mcp_server_id = upstream_srv.id
        new_store.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(new_store)

        return ProvisionedStoreResponse(
            id=new_store.id,
            name=new_store.name,
            slug=new_store.slug,
            namespace=new_store.namespace,
            owner_user_id=new_store.owner_user_id,
            status=new_store.status,
            store_url=new_store.store_url,
            mcp_server_id=upstream_srv.id,
            mcp_server_slug=upstream_slug,
            created_at=new_store.created_at,
            updated_at=new_store.updated_at
        )

    except Exception as exc:
        new_store.status = StoreStatus.FAILED.value
        new_store.error_reason = str(exc)
        new_store.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Store provisioning failed: {str(exc)}")

@router.delete("/{store_id}", status_code=status.HTTP_200_OK)
async def delete_store(
    store_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_auth)
):
    """Clean teardown: deletes UpstreamServer, purges K8s namespace, and removes DB row."""
    stmt = select(ProvisionedStore).where(ProvisionedStore.id == store_id)
    store = (await db.execute(stmt)).scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found.")

    if not auth.is_admin and store.owner_user_id != auth.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this store.")

    store_slug = store.slug

    # 1. Await K8s teardown cleanly to avoid orphaned resources
    try:
        await k8s_provisioner.deprovision_store(store_slug)
    except Exception as exc:
        pass

    # 2. Delete associated UpstreamServer from Gateway
    if store.mcp_server_id:
        srv_stmt = select(UpstreamServer).where(UpstreamServer.id == store.mcp_server_id)
        srv = (await db.execute(srv_stmt)).scalar_one_or_none()
        if srv:
            await db.delete(srv)

    # 3. Finally delete Store record from DB
    await db.delete(store)
    await db.commit()

    return {"message": f"Store '{store_slug}' and its Kubernetes namespace have been torn down."}
