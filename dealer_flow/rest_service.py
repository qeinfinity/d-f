from fastapi import FastAPI, Response, status
from dealer_flow.redis_stream import get_redis, STREAM_KEY_METRICS
import orjson
import asyncio

app = FastAPI()

@app.get("/snapshot")
async def snapshot():
    redis = await get_redis()
    last = await redis.xrevrange(STREAM_KEY_METRICS, count=1)
    if not last:
        # metrics not produced yet → 204 No Content
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return orjson.loads(last[0][1][b"d"])






