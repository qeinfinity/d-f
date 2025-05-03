import aioredis
from dealer_flow.config import settings

STREAM_KEY_RAW = "dealer_raw"
STREAM_KEY_METRICS = "dealer_metrics"

async def get_redis():
    return await aioredis.from_url(settings.redis_url, decode_responses=False)
