#!/usr/bin/env bash
# ==============================================================================
# Urumi Platform — Local Kubernetes Deployment Engine (Kind / k3d / Minikube)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

CLUSTER_NAME="${CLUSTER_NAME:-urumi-local}"
NAMESPACE="${NAMESPACE:-urumi}"

echo "========================================================================"
echo "🚀 URUMI PLATFORM: LOCAL KUBERNETES DEPLOYMENT"
echo "========================================================================"

# 1. Verify Prerequisites
echo "==> [1/6] Verifying toolchain prerequisites..."
command -v docker >/dev/null 2>&1 || { echo "❌ docker is required. Aborting."; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl is required. Aborting."; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "❌ helm is required. Aborting."; exit 1; }

# Detect cluster runtime
CLUSTER_RUNNER="none"
if command -v k3d >/dev/null 2>&1; then
  CLUSTER_RUNNER="k3d"
elif command -v kind >/dev/null 2>&1; then
  CLUSTER_RUNNER="kind"
elif command -v minikube >/dev/null 2>&1; then
  CLUSTER_RUNNER="minikube"
else
  echo "⚠️  Neither k3d, kind, nor minikube found. Assuming external active context:"
  kubectl config current-context || true
fi

# 2. Provision Cluster if needed
echo "==> [2/6] Ensuring Kubernetes cluster is ready..."
if [ "$CLUSTER_RUNNER" = "k3d" ]; then
  if ! k3d cluster list | grep -q "$CLUSTER_NAME"; then
    echo "Creating k3d cluster '$CLUSTER_NAME' with ingress ports 80/443..."
    k3d cluster create "$CLUSTER_NAME" \
      --port "80:80@loadbalancer" \
      --port "443:443@loadbalancer" \
      --k3s-arg "--disable=traefik@server:0"
  fi
elif [ "$CLUSTER_RUNNER" = "kind" ]; then
  if ! kind get clusters | grep -q "^$CLUSTER_NAME$"; then
    echo "Creating Kind cluster '$CLUSTER_NAME' with extraPortMappings..."
    cat <<EOF | kind create cluster --name "$CLUSTER_NAME" --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
  extraPortMappings:
  - containerPort: 80
    hostPort: 80
    protocol: TCP
  - containerPort: 443
    hostPort: 443
    protocol: TCP
EOF
  fi
fi

# 3. Build Docker Images
echo "==> [3/6] Building application and MCP container images..."
cd "$ROOT_DIR"

echo "  -> Building urumi/woocommerce-mcp:latest..."
docker build -t urumi/woocommerce-mcp:latest -f mcp-servers/woocommerce-mcp/Dockerfile mcp-servers/woocommerce-mcp

echo "  -> Building urumi/promos-analytics-mcp:latest..."
docker build -t urumi/promos-analytics-mcp:latest -f mcp-servers/promos-analytics-mcp/Dockerfile mcp-servers/promos-analytics-mcp

echo "  -> Building urumi/ops-notifier-mcp:latest..."
docker build -t urumi/ops-notifier-mcp:latest -f mcp-servers/ops-notifier-mcp/Dockerfile mcp-servers/ops-notifier-mcp

echo "  -> Building urumi/gateway-backend:latest..."
docker build -t urumi/gateway-backend:latest -f gateway-backend/Dockerfile gateway-backend

echo "  -> Building urumi/dashboard:latest..."
docker build -t urumi/dashboard:latest -f dashboard/Dockerfile dashboard

# 4. Load Images into Cluster
echo "==> [4/6] Loading container images into cluster..."
if [ "$CLUSTER_RUNNER" = "k3d" ]; then
  k3d image import \
    urumi/woocommerce-mcp:latest \
    urumi/promos-analytics-mcp:latest \
    urumi/ops-notifier-mcp:latest \
    urumi/gateway-backend:latest \
    urumi/dashboard:latest \
    -c "$CLUSTER_NAME"
elif [ "$CLUSTER_RUNNER" = "kind" ]; then
  kind load docker-image \
    urumi/woocommerce-mcp:latest \
    urumi/promos-analytics-mcp:latest \
    urumi/ops-notifier-mcp:latest \
    urumi/gateway-backend:latest \
    urumi/dashboard:latest \
    --name "$CLUSTER_NAME"
fi

# 5. Helm Deployment
echo "==> [5/6] Deploying Helm release 'urumi' with values-local.yaml..."
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install urumi "${ROOT_DIR}/charts/urumi-platform" \
  --namespace "$NAMESPACE" \
  -f "${ROOT_DIR}/charts/urumi-platform/values-local.yaml" \
  --timeout 10m \
  --wait

# 6. Verify Deployment Status
echo "==> [6/6] Verifying cluster workloads..."
kubectl get pods -n "$NAMESPACE"
kubectl get pvc -n "$NAMESPACE"
kubectl get ingress -n "$NAMESPACE"

echo ""
echo "========================================================================"
echo "🎉 LOCAL DEPLOYMENT SUCCESSFUL!"
echo "========================================================================"
echo "Access Points (ensure 127.0.0.1.nip.io resolves to your host/cluster IP):"
echo "  • React UI Dashboard:     http://app.127.0.0.1.nip.io"
echo "  • MCP Gateway & Stream:   http://gateway.127.0.0.1.nip.io/mcp"
echo "  • WooCommerce Storefront: http://store.127.0.0.1.nip.io"
echo "  • WordPress Admin:        http://store.127.0.0.1.nip.io/wp-admin"
echo "========================================================================"
