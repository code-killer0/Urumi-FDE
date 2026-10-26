import ipaddress
import socket
from urllib.parse import urlparse
from fastapi import HTTPException, status
from app.config import settings

# Disallowed internal networks and cloud metadata
BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.169.254/32"),  # Cloud Instance Metadata Service (AWS/GCP/Azure)
    ipaddress.ip_network("169.254.0.0/16"),      # Link-local addresses
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved
]

ALLOWED_K8S_PORTS = {80, 443, 8000, 8001, 8002, 8003, 8080, 8443, 9000}

def validate_upstream_url(url: str) -> str:
    """
    Validates upstream target URLs to prevent SSRF (Server-Side Request Forgery).
    Blocks cloud instance metadata (169.254.169.254), link-local, loopback,
    and non-HTTP(S) schemes, while explicitly permitting internal Kubernetes
    services matching '*.svc.cluster.local' on approved ports.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL protocol '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upstream URL must include a valid hostname."
        )

    target_port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # 1. Block Cloud Metadata attacks immediately
    if hostname == "169.254.169.254" or "169.254" in hostname or "metadata.google.internal" in hostname:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to Cloud Instance Metadata Services (169.254.169.254) is strictly prohibited."
        )

    # 2. Explicitly permit Kubernetes cluster-internal domain services
    if hostname.endswith(".svc.cluster.local") or hostname.endswith(".svc"):
        if target_port not in ALLOWED_K8S_PORTS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Port {target_port} is not in the approved Kubernetes internal service port list."
            )
        return url

    # 3. Development / Localhost allowed domains check
    if hostname in settings.ALLOWED_HOST_DOMAINS:
        return url

    # 4. Resolve hostname IP address to guard against DNS rebinding
    try:
        resolved_ips = socket.getaddrinfo(hostname, target_port)
        for item in resolved_ips:
            ip_str = item[4][0]
            ip_obj = ipaddress.ip_address(ip_str)

            for blocked in BLOCKED_NETWORKS:
                if ip_obj in blocked:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Access to forbidden network range {blocked} is prohibited."
                    )

            # Block loopback if not explicitly permitted
            if ip_obj.is_loopback and not settings.ALLOW_INTERNAL_IPS:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Loopback addresses are forbidden."
                )

            # Block private networks if ALLOW_INTERNAL_IPS is False
            if not settings.ALLOW_INTERNAL_IPS and ip_obj.is_private:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Direct access to private network IP {ip_str} is forbidden."
                )

    except socket.gaierror:
        # If running inside Kubernetes, internal service names might not resolve
        # outside the cluster DNS; if it's in the allowed domains, it passes.
        if hostname not in settings.ALLOWED_HOST_DOMAINS and not hostname.endswith(".cluster.local"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Hostname '{hostname}' could not be resolved."
            )

    return url
