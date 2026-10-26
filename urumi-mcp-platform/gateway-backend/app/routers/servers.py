from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import UpstreamServer, ServerStatus
from app.schemas import UpstreamServerCreate, UpstreamServerUpdate, UpstreamServerResponse
from app.security import require_admin, require_auth, AuthContext, encrypt_credential
from app.ssrf_guard import validate_upstream_url
from app.upstream_manager import upstream_manager
from app.k8s_provisioner import k8s_provisioner

router = APIRouter(prefix="/servers", tags=["Upstream MCP Servers"])

@router.get("", response_model=List[UpstreamServerResponse])
async def list_servers(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_auth)
):
    stmt = select(UpstreamServer).order_by(UpstreamServer.id.asc())
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("", response_model=UpstreamServerResponse, status_code=status.HTTP_201_CREATED)
async def register_server(
    server_in: UpstreamServerCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    # Check duplicates
    stmt = select(UpstreamServer).where((UpstreamServer.name == server_in.name) | (UpstreamServer.slug == server_in.slug))
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Server with this name or slug already exists.")

    is_hosted = server_in.is_hosted or bool(server_in.container_image)
    server_url = server_in.url

    # Standout #5: Deploy hosted MCP by container image
    if is_hosted:
        if not server_in.container_image:
            raise HTTPException(status_code=400, detail="Container image is required for hosted MCP deployment.")
        server_url = await k8s_provisioner.deploy_hosted_mcp(
            slug=server_in.slug,
            container_image=server_in.container_image,
            env_vars=server_in.env_vars
        )
    else:
        if not server_url:
            raise HTTPException(status_code=400, detail="URL is required for non-hosted external MCP servers.")
        validate_upstream_url(server_url)

    encrypted_cred = encrypt_credential(server_in.credential) if server_in.credential else None

    new_server = UpstreamServer(
        name=server_in.name,
        slug=server_in.slug,
        url=server_url.rstrip("/"),
        auth_header_name=server_in.auth_header_name,
        encrypted_credential=encrypted_cred,
        enabled=server_in.enabled,
        is_hosted=is_hosted,
        container_image=server_in.container_image,
        status=ServerStatus.CONNECTED.value,
        cached_tools=[]
    )
    db.add(new_server)
    await db.commit()
    await db.refresh(new_server)

    # Immediately probe and sync tools
    await upstream_manager.probe_and_sync_server(new_server, db)
    await db.refresh(new_server)
    return new_server

@router.get("/{server_id}", response_model=UpstreamServerResponse)
async def get_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_auth)
):
    stmt = select(UpstreamServer).where(UpstreamServer.id == server_id)
    server = (await db.execute(stmt)).scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Upstream server not found.")
    return server

@router.patch("/{server_id}", response_model=UpstreamServerResponse)
async def update_server(
    server_id: int,
    patch: UpstreamServerUpdate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    stmt = select(UpstreamServer).where(UpstreamServer.id == server_id)
    server = (await db.execute(stmt)).scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Upstream server not found.")

    if patch.name is not None:
        server.name = patch.name
    if patch.url is not None:
        validate_upstream_url(patch.url)
        server.url = patch.url.rstrip("/")
    if patch.credential is not None:
        server.encrypted_credential = encrypt_credential(patch.credential)
    if patch.enabled is not None:
        server.enabled = patch.enabled

    await db.commit()
    await db.refresh(server)
    return server

@router.delete("/{server_id}", status_code=status.HTTP_200_OK)
async def delete_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    """Deletes an upstream server. If hosted in K8s, tears down Deployment & Service."""
    stmt = select(UpstreamServer).where(UpstreamServer.id == server_id)
    server = (await db.execute(stmt)).scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Upstream server not found.")

    if server.is_hosted:
        await k8s_provisioner.deprovision_hosted_mcp(server.slug)

    await db.delete(server)
    await db.commit()
    return {"message": f"Server '{server.slug}' deleted successfully."}

@router.post("/{server_id}/sync-tools", response_model=UpstreamServerResponse)
async def sync_server_tools(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_admin)
):
    stmt = select(UpstreamServer).where(UpstreamServer.id == server_id)
    server = (await db.execute(stmt)).scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Upstream server not found.")

    await upstream_manager.probe_and_sync_server(server, db)
    await db.refresh(server)
    return server
