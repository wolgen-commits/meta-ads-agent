#!/bin/bash
set -e
echo "[Startup] Starting server..."
exec uvicorn api_server:app --host 0.0.0.0 --port ${PORT:-8000}
