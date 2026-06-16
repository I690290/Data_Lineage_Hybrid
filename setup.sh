#!/usr/bin/env bash
# Hybrid Data Lineage Engine - one-shot environment setup.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Checking prerequisites"
command -v uv >/dev/null 2>&1 || {
    echo "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }

echo "==> Python dependencies (uv sync)"
uv sync

if [ ! -f .env ]; then
    echo "==> Creating .env from .env.example  (edit it: AWS or NVIDIA credentials)"
    cp .env.example .env
fi

if command -v npm >/dev/null 2>&1; then
    echo "==> Frontend dependencies (npm install)"
    (cd frontend && npm install)
else
    echo "!! npm not found - skipping frontend install"
fi

if command -v docker >/dev/null 2>&1; then
    echo "==> Starting Neo4j container"
    docker compose up -d neo4j
    echo "    Neo4j browser: http://localhost:7474  (neo4j / \$NEO4J_PASSWORD)"
else
    echo "!! docker not found - start Neo4j manually (see README)"
fi

cat <<'EOF'

Setup complete. Next steps:
  1. Edit .env            (Bedrock or NVIDIA credentials, Neo4j password)
  2. Edit config.yaml     (ai.provider: bedrock | nvidia)
  3. uv run python main.py ingest          # parse mock-code -> Neo4j
     uv run python main.py ingest --no-ai  # deterministic-only
  4. uv run uvicorn api.main:app --reload  # FastAPI on :8000
  5. cd frontend && npm run dev            # Lineage UI on :5173
EOF
