from fastapi import FastAPI
from dealer_flow.redis_stream import get_redis, STREAM_KEY_METRICS
import orjson
import asyncio

app = FastAPI()

@app.get("/snapshot")
async def snapshot():
    redis = await get_redis()
    last = await redis.xrevrange(STREAM_KEY_METRICS, count=1)
    return orjson.loads(list(last)[0][1][b"d"])
