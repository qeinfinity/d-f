#!/bin/sh
set -e

echo "Starting Deribit WebSocket collector..."
python -m dealer_flow.deribit_ws &

echo "Starting Processor..."
python -m dealer_flow.processor &

echo "Starting Uvicorn API server..."
uvicorn dealer_flow.rest_service:app --host 0.0.0.0 --port 8000