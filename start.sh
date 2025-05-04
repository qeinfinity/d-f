#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Start the Deribit WebSocket collector in the background
echo "Starting Deribit WebSocket collector..."
python -m dealer_flow.deribit_ws &

# Start the Uvicorn server for the API in the foreground
echo "Starting Uvicorn API server..."
uvicorn dealer_flow.rest_service:app --host 0.0.0.0 --port 8000