#!/usr/bin/env bash
# Luna SGP 四层微服务启动脚本
# L1(:8001) / L4(:8003) 用 .venv ; L2(:8002) 用 .venv_geo (geoopt+torch)
set -euo pipefail
cd "$(dirname "$0")"

start() {
  local name="$1" venv="$2" app="$3" port="$4"
  if curl -sf -m 2 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
    echo "[skip] $name :$port already healthy"
    return
  fi
  nohup "$venv/bin/python" -m uvicorn "$app" --host 127.0.0.1 --port "$port" \
    --log-level warning >"$(dirname "$app")/server.log" 2>&1 &
  echo "[up]   $name :$port (pid $!)"
}

start L1-Graph .venv      l1_graph.service:app 8001
start L2-Geo   .venv_geo  l2_geo.service:app   8002
start L4-Mind  .venv      l4_mind.service:app  8003
start L3-Topo  .venv_topo l3_topo.service:app  8004

echo "waiting for health..."
for p in 8001 8002 8003 8004; do
  for i in {1..20}; do
    if curl -sf -m 2 "http://127.0.0.1:$p/health" >/dev/null 2>&1; then
      echo "  :$p ok -> $(curl -s http://127.0.0.1:$p/health)"; break
    fi
    sleep 0.5
  done
done
