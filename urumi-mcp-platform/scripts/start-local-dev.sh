#!/usr/bin/env bash
# ==============================================================================
# Urumi Platform — Quick Local Development Runner
# Starts 3 Upstream MCP Servers, Gateway Backend, and Dashboard UI
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$ROOT_DIR"

# Activate Python venv
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f "../.venv/bin/activate" ]; then
    source ../.venv/bin/activate
fi

echo "========================================================================"
echo "🚀 STARTING URUMI PLATFORM (LOCAL DEVELOPMENT PROCESSES)"
echo "========================================================================"

# Trap to kill all background subprocesses on Ctrl+C or exit
PIDS=()
cleanup() {
    echo ""
    echo "🛑 Shutting down all Urumi services..."
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo "✓ All services stopped."
}
trap cleanup SIGINT SIGTERM EXIT

# 1. Start WooCommerce MCP (Port 8001)
echo "▶ [1/5] Starting WooCommerce MCP server on :8001..."
python3 mcp-servers/woocommerce-mcp/server.py &
PIDS+=($!)

# 2. Start Promos Analytics MCP (Port 8002)
echo "▶ [2/5] Starting Promos Analytics MCP server on :8002..."
python3 mcp-servers/promos-analytics-mcp/server.py &
PIDS+=($!)

# 3. Start Ops Notifier MCP (Port 8003)
echo "▶ [3/5] Starting Ops Notifier MCP server on :8003..."
python3 mcp-servers/ops-notifier-mcp/server.py &
PIDS+=($!)

# Wait 2 seconds for MCP servers to bind
sleep 2

# 4. Start Gateway Backend (Port 8000)
echo "▶ [4/5] Starting Gateway Backend on :8000..."
(cd gateway-backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000) &
PIDS+=($!)

# Wait 2 seconds for Gateway to seed DB and bind
sleep 2

# 5. Start Dashboard UI (Port 3000)
echo "▶ [5/5] Starting Dashboard UI on :3000..."
(cd dashboard && npm run dev -- --host 0.0.0.0 --port 3000) &
PIDS+=($!)

echo ""
echo "========================================================================"
echo "🎉 ALL URUMI SERVICES RUNNING!"
echo "========================================================================"
echo "  • Dashboard UI:        http://localhost:3000"
echo "  • Gateway Healthz:     http://localhost:8000/healthz"
echo "  • MCP Gateway /mcp:    http://localhost:8000/mcp"
echo "  • API Docs (Swagger):  http://localhost:8000/docs"
echo "  • Woo MCP:             http://localhost:8001/healthz"
echo "  • Promos MCP:          http://localhost:8002/healthz"
echo "  • Ops MCP:             http://localhost:8003/healthz"
echo "========================================================================"
echo "Press Ctrl+C at any time to stop all services."
echo ""

wait
