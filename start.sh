#!/bin/bash
set -e
echo "[Startup] Installing Playwright Chromium..."
playwright install chromium --with-deps
echo "[Startup] Playwright ready. Starting server..."
exec uvicorn api_server:app --host 0.0.0.0 --port $PORT
