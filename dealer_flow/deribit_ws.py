"""
Async collector for Deribit public data:
- ticker (includes greeks, IV, mark price)
- book (needed for OI per strike)
Streams raw JSON into Redis Streams.
"""
import asyncio
import json
import uuid
import websockets
from dealer_flow.config import settings
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW

SUBS = [
    f"ticker.{settings.currency}-PERPETUAL.raw",
    f"book.{settings.currency}-PERPETUAL.100ms",
    f"deribit_price_index.{settings.currency.lower()}_usd",
]

async def subscribe(ws):
    req = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "public/subscribe",
        "params": {"channels": SUBS},
    }
    await ws.send(json.dumps(req))

async def run():
    redis = await get_redis()
    async with websockets.connect(settings.deribit_ws, ping_interval=20) as ws:
        await subscribe(ws)
        async for msg in ws:
            await redis.xadd(STREAM_KEY_RAW, {"d": msg})

if __name__ == "__main__":
    asyncio.run(run())
