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
import sys

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
        print("PROCESSOR: Starting up...", file=sys.stderr) # Use stderr for visibility
        redis = await get_redis()
        await ensure_group(redis)
        print("PROCESSOR: Redis connection and group OK.", file=sys.stderr)

        prices = deque(maxlen=1)
        tick_times = deque(maxlen=1000)

        while True:
            try: # Add try/except
                print(f"PROCESSOR: Blocking read on {STREAM_KEY_RAW}...", file=sys.stderr)
                resp = await redis.xreadgroup(
                    GROUP, CONSUMER, streams={STREAM_KEY_RAW: ">"}, count=100, block=BLOCK_MS
                )
                print(f"PROCESSOR: Read response: {resp is not None}", file=sys.stderr)

                if not resp:
                    # idle: still publish heartbeat every 2 s (or less frequently for debug)
                    await maybe_publish(redis, prices, tick_times, "idle")
                    await asyncio.sleep(1) # Add sleep to prevent busy-loop if idle
                    continue

                for stream_name, messages in resp:
                    print(f"PROCESSOR: Processing {len(messages)} messages from {stream_name}", file=sys.stderr)
                    for _id, data in messages:
                        try:
                            raw: bytes = data[b"d"]
                            tick = orjson.loads(raw)

                            # More robust checking
                            params = tick.get("params")
                            if isinstance(params, dict):
                                ch = params.get("channel", "N/A")
                                tick_data = params.get("data")
                                print(f"PROCESSOR: Parsed tick from channel: {ch}", file=sys.stderr) # Log channel

                                if isinstance(tick_data, dict):
                                     if ch.startswith("ticker") and "mark_price" in tick_data:
                                         try:
                                             price = float(tick_data["mark_price"])
                                             prices.append(price)
                                             print(f"PROCESSOR: Updated price: {price}", file=sys.stderr)
                                         except (ValueError, TypeError):
                                              print(f"PROCESSOR: ERROR converting mark_price: {tick_data.get('mark_price')}", file=sys.stderr)
                                     else:
                                         # Log ticks that have data but aren't the expected ticker/price
                                         print(f"PROCESSOR: Skipping tick, not target ticker/price. Chan: {ch}, Keys: {list(tick_data.keys())}", file=sys.stderr)
                                else:
                                    # Log ticks that have params but no 'data' dict
                                     print(f"PROCESSOR: Skipping tick, no data dict. Chan: {ch}", file=sys.stderr)

                            else:
                                # Log messages without 'params' entirely (e.g., maybe JSON-RPC responses?)
                                print(f"PROCESSOR: Skipping message, no 'params' key. Tick: {tick}", file=sys.stderr)

                            tick_times.append(time.time())
                        except orjson.JSONDecodeError as e_json:
                            print(f"PROCESSOR: ERROR decoding JSON for message {_id}: {e_json}\nRaw: {raw}", file=sys.stderr)
                        except Exception as e_parse:
                             print(f"PROCESSOR: ERROR parsing message {_id}: {e_parse}\nData: {data}", file=sys.stderr)

                await maybe_publish(redis, prices, tick_times, "after_read")
                # Acknowledge messages if using XREADGROUP properly (optional for now)
                # await redis.xack(STREAM_KEY_RAW, GROUP, *[mid for mid, _ in messages])

            except Exception as e_loop:
                 print(f"PROCESSOR: ERROR in main loop: {e_loop}", file=sys.stderr)
                 await asyncio.sleep(5) # Prevent rapid crash loop


async def maybe_publish(redis, prices, tick_times, source="unknown"):
    now = time.time()
    # prune tick_times older than 1 s
    while tick_times and now - tick_times[0] > 1.0:
        tick_times.popleft()

    if not prices:
        print(f"PROCESSOR ({source}): No prices yet, skipping publish.", file=sys.stderr)
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
    try:
        print(f"PROCESSOR ({source}): Publishing metrics: {payload}", file=sys.stderr)
        await redis.xadd(STREAM_KEY_METRICS, {"d": orjson.dumps(payload)})
        print(f"PROCESSOR ({source}): Publish successful.", file=sys.stderr)
    except Exception as e_pub:
            print(f"PROCESSOR ({source}): ERROR publishing: {e_pub}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(processor())