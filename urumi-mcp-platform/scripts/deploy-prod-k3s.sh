#!/usr/bin/env bash
# ==============================================================================
# Urumi Platform — Production k3s VPS Deployment Engine with TLS & Traefik
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Auto-detect K3s kubeconfig if not set
if [ -z "${KUBECONFIG:-}" ]; then
  if [ -f "/etc/rancher/k3s/k3s.yaml" ]; then
    export KUBECONFIG="/etc/rancher/k3s/k3s.yaml"
  elif [ -f "${HOME}/.kube/config" ]; then
    export KUBECONFIG="${HOME}/.kube/config"
  fi
fi
export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

NAMESPACE="${NAMESPACE:-urumi}"
VPS_IP="${VPS_IP:-}"
DOMAIN="${DOMAIN:-}"

echo "========================================================================"
echo "🚀 URUMI PLATFORM: PRODUCTION K3S VPS DEPLOYMENT"
echo "========================================================================"

# Auto-detect Public IP if not provided
if [ -z "$DOMAIN" ] && [ -z "$VPS_IP" ]; then
  VPS_IP=$(curl -s -4 ifconfig.me || curl -s -4 icanhazip.com || echo "")
  if [ -n "$VPS_IP" ]; then
    DOMAIN="${VPS_IP}.nip.io"
    echo "ℹ️  Auto-detected Public VPS IP: $VPS_IP -> Domain: $DOMAIN"
  else
    echo "❌ Could not determine public IP. Please pass DOMAIN=<your-domain> or VPS_IP=<ip>"; exit 1;
  fi
elif [ -n "$VPS_IP" ] && [ -z "$DOMAIN" ]; then
  DOMAIN="${VPS_IP}.nip.io"
fi

echo "Deploying to Production Domain: $DOMAIN"

# 1. Verify Toolchain
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl is required. Aborting."; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "❌ helm is required. Aborting."; exit 1; }

# 2. Check k3s Node
kubectl get nodes -o wide

# 3. Create Namespace
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# 4. Inject Production Secrets Securely at Runtime (No Secrets in Git)
echo "==> [1/4] Injecting production secrets into cluster..."
JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"
FERNET_KEY="${FERNET_KEY:-$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || openssl rand -base64 32)}"
MCP_UPSTREAM_TOKEN="${MCP_UPSTREAM_TOKEN:-$(openssl rand -hex 24)}"
WC_CONSUMER_KEY="${WC_CONSUMER_KEY:-ck_$(openssl rand -hex 20)}"
WC_CONSUMER_SECRET="${WC_CONSUMER_SECRET:-cs_$(openssl rand -hex 20)}"
MARIADB_PASSWORD="${MARIADB_PASSWORD:-$(openssl rand -hex 16)}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -hex 16)}"

kubectl create secret generic urumi-prod-secrets -n "$NAMESPACE" \
  --from-literal=JWT_SECRET="$JWT_SECRET" \
  --from-literal=FERNET_KEY="$FERNET_KEY" \
  --from-literal=MCP_UPSTREAM_TOKEN="$MCP_UPSTREAM_TOKEN" \
  --from-literal=WC_CONSUMER_KEY="$WC_CONSUMER_KEY" \
  --from-literal=WC_CONSUMER_SECRET="$WC_CONSUMER_SECRET" \
  --from-literal=MARIADB_ROOT_PASSWORD="$MARIADB_PASSWORD" \
  --from-literal=MARIADB_PASSWORD="$MARIADB_PASSWORD" \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  --from-literal=DATABASE_URL="postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@urumi-postgres:5432/urumi" \
  --dry-run=client -o yaml | kubectl apply -f -

# 5. Ensure Cert-Manager ClusterIssuer for Let's Encrypt exists
echo "==> [2/4] Verifying cert-manager and ClusterIssuer..."
if ! kubectl get clusterissuer letsencrypt-prod >/dev/null 2>&1; then
  echo "Installing cert-manager Let's Encrypt ClusterIssuer..."
  cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@${DOMAIN}
    privateKeySecretRef:
      name: letsencrypt-prod-account-key
    solvers:
    - http01:
        ingress:
          class: traefik
EOF
fi

# 6. Deploy with Helm values-prod.yaml + dynamic domain overrides
echo "==> [3/4] Running Helm upgrade --install with production configuration..."
helm upgrade --install urumi "${ROOT_DIR}/charts/urumi-platform" \
  --namespace "$NAMESPACE" \
  -f "${ROOT_DIR}/charts/urumi-platform/values-prod.yaml" \
  --set global.domain="$DOMAIN" \
  --set global.imagePullPolicy="IfNotPresent" \
  --set ingress.hosts.store="store.${DOMAIN}" \
  --set ingress.hosts.gateway="gateway.${DOMAIN}" \
  --set ingress.hosts.dashboard="app.${DOMAIN}" \
  --set ingress.tls[0].hosts[0]="store.${DOMAIN}" \
  --set ingress.tls[0].secretName="urumi-tls-store" \
  --set ingress.tls[1].hosts[0]="gateway.${DOMAIN}" \
  --set ingress.tls[1].secretName="urumi-tls-gateway" \
  --set ingress.tls[2].hosts[0]="app.${DOMAIN}" \
  --set ingress.tls[2].secretName="urumi-tls-app" \
  --timeout 12m \
  --wait

# 7. Verification
echo "==> [4/4] Verifying production deployment..."
kubectl get pods -n "$NAMESPACE"
kubectl get ingress -n "$NAMESPACE"
kubectl get certificates -n "$NAMESPACE" || true

echo ""
echo "========================================================================"
echo "🎉 PRODUCTION VPS DEPLOYMENT COMPLETED!"
echo "========================================================================"
echo "Production Endpoints:"
echo "  • Dashboard UI:           https://app.${DOMAIN}"
echo "  • MCP Gateway & Stream:   https://gateway.${DOMAIN}/mcp"
echo "  • WooCommerce Storefront: https://store.${DOMAIN}"
echo "========================================================================"
