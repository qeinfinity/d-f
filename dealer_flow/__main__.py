"""
Convenience entrypoint: launches collector and API concurrently
"""
import asyncio
from dealer_flow.deribit_ws import run as ws_run
from dealer_flow.rest_service import app  # ensures FastAPI import
import uvicorn

async def main():
    task_ws = asyncio.create_task(ws_run())
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await asyncio.gather(task_ws, server.serve())

if __name__ == "__main__":
    asyncio.run(main())
