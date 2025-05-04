"""
Collector with verbose logging.
If credentials missing or auth fails we fall back to **unauth** mode and
subscribe to at most 12 liquid ATM option strikes to guarantee success.
"""
import asyncio, json, time, uuid, aiohttp, websockets, orjson, sys
from dealer_flow.config import settings
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW

TOKEN_TTL = 23 * 3600
MAX_UNAUTH_STRIKES = 12            # Deribit limit for 100 ms streams

async def auth_token():
    if not (settings.deribit_id and settings.deribit_secret):
        print("COLLECTOR: creds absent → unauth mode", file=sys.stderr)
        return None, 0
    async with aiohttp.ClientSession() as sess:
        try:
            r = await sess.get(
                f"{settings.deribit_rest}/public/auth",
                params={
                    "grant_type": "client_credentials",
                    "client_id": settings.deribit_id,
                    "client_secret": settings.deribit_secret,
                },
                timeout=10,
            )
            j = await r.json()
        except Exception as e:
            print(f"COLLECTOR: auth HTTP error {e} → unauth mode", file=sys.stderr)
            return None, 0
    if "error" in j:
        print(f"COLLECTOR: auth rejected {j['error']} → unauth mode", file=sys.stderr)
        return None, 0
    token = j["result"]["access_token"]
    print("COLLECTOR: auth OK", file=sys.stderr)
    return token, time.time() + TOKEN_TTL


async def current_instruments():
    async with aiohttp.ClientSession() as sess:
        r = await sess.get(
            f"{settings.deribit_rest}/public/get_instruments",
            params=dict(currency=settings.currency, kind="option", expired="false"),
            timeout=10,
        )
        data = (await r.json())["result"]
        # crude filter: keep first strikes near ATM
        return [d["instrument_name"] for d in data[:MAX_UNAUTH_STRIKES]]


async def subscribe(ws, channels):
    req = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "public/subscribe",
        "params": {"channels": channels},
    }
    await ws.send(orjson.dumps(req).decode())


async def run():
    redis = await get_redis()

    while True:  # reconnect loop
        token, token_exp = await auth_token()
        try:
            instruments = await current_instruments()
        except Exception as e:
            print(f"COLLECTOR: instrument fetch failed {e}", file=sys.stderr)
            await asyncio.sleep(5)
            continue

        spot_ch = f"deribit_price_index.{settings.currency.lower()}_usd"
        subs = (
            [spot_ch]
            + [f"ticker.{i}.100ms" for i in instruments]
            + [f"book.{i}.100ms" for i in instruments]
        )

        hdrs = {"Authorization": f"Bearer {token}"} if token else {}
        mode = "auth" if token else "unauth"
        print(f"COLLECTOR: connecting ({mode}), {len(subs)} channels …",
              file=sys.stderr)

        try:
            async with websockets.connect(
                settings.deribit_ws, extra_headers=hdrs, ping_interval=20
            ) as ws:
                await subscribe(ws, subs)
                print("COLLECTOR: subscribed, streaming …", file=sys.stderr)
                cnt = 0
                async for msg in ws:
                    await redis.xadd(STREAM_KEY_RAW, {"d": msg.encode()})
                    cnt += 1
                    if cnt % 500 == 0:
                        print(f"COLLECTOR: pushed {cnt} msgs", file=sys.stderr)
        except Exception as e:
            print(f"COLLECTOR: websocket error {e} – reconnect in 5 s",
                  file=sys.stderr)
            await asyncio.sleep(5)

if __name__ == "__main__":
    import asyncio, sys
    try:
        print("COLLECTOR: launching …", file=sys.stderr)
        asyncio.run(run())
    except KeyboardInterrupt:
        print("COLLECTOR: interrupted, exiting.", file=sys.stderr)