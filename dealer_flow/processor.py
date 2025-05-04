# ---------- NEW FILE: dealer_flow/processor.py ----------
"""
Processor: reads raw Deribit messages from Redis Stream `dealer_raw`,
derives minimal metrics, writes JSON blob to `dealer_metrics`.

This first iteration *only*:
• parses ticker price from perpetual feed
• counts messages per rolling 1-second window (msg_rate)
• publishes stub NGI/VSS/CHL/HPP so the dashboard endpoint works

Subsequent iterations will:
• ingest options OI, compute full greeks, HPP, scenario bucket
"""

import asyncio, orjson, time
from collections import deque, defaultdict
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW, STREAM_KEY_METRICS


GROUP = "processor"
CONSUMER = "p1"
BLOCK_MS = 200  # long-poll up to 0.2 s (fits 200 ms e2e budget)


async def ensure_group(r):
    try:
        await r.xgroup_create(STREAM_KEY_RAW, GROUP, id="$", mkstream=True)
    except Exception as e:
        # BUSYGROUP means it already exists
        if "BUSYGROUP" not in str(e):
            raise


async def processor():
    redis = await get_redis()
    await ensure_group(redis)

    prices = deque(maxlen=1)  # latest spot price
    tick_times = deque(maxlen=1000)  # timestamps for msg-rate calc

    while True:
        resp = await redis.xreadgroup(
            GROUP, CONSUMER, streams={STREAM_KEY_RAW: ">"}, count=100, block=BLOCK_MS
        )
        if not resp:
            # idle: still publish heartbeat every 2 s
            await maybe_publish(redis, prices, tick_times)
            continue

        for _, messages in resp:
            for _id, data in messages:
                raw: bytes = data[b"d"]
                tick = orjson.loads(raw)
                ch = tick.get("params", {}).get("channel", "")
                if ch.startswith("ticker") and "mark_price" in tick["params"]["data"]:
                    prices.append(float(tick["params"]["data"]["mark_price"]))
                tick_times.append(time.time())

        await maybe_publish(redis, prices, tick_times)


async def maybe_publish(redis, prices, tick_times):
    now = time.time()
    # prune tick_times older than 1 s
    while tick_times and now - tick_times[0] > 1.0:
        tick_times.popleft()

    if not prices:
        return  # nothing yet

    payload = {
        "ts": now,
        "price": prices[-1],
        "msg_rate": len(tick_times),
        # stub metrics
        "NGI": 0.0,
        "VSS": 0.0,
        "CHL_24h": 0.0,
        "HPP": 0.0,
    }
    await redis.xadd(STREAM_KEY_METRICS, {"d": orjson.dumps(payload)})


if __name__ == "__main__":
    asyncio.run(processor())