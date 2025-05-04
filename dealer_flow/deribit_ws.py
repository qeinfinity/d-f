"""
Async collector for Deribit public data:
- ticker (includes greeks, IV, mark price)
- book (needed for OI per strike)
Streams raw JSON into Redis Streams.
"""
import asyncio, json, time, uuid, aiohttp, websockets, orjson
from dealer_flow.config import settings
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW

TOKEN_TTL = 23 * 3600  # renew 1 h before expiry
FILTER_MONEYNESS = 0.10  # ±10 %
MIN_OI_PCT = 0.01        # 1 % of total OI

async def auth_token():
    async with aiohttp.ClientSession() as sess:
        r = await sess.get(
            f"{settings.deribit_rest}/public/auth",
            params={
                "grant_type": "client_credentials",
                "client_id": settings.deribit_id,
                "client_secret": settings.deribit_secret,
            },
        )
        j = await r.json()
        return j["result"]["access_token"], time.time() + TOKEN_TTL


async def current_instruments():
    async with aiohttp.ClientSession() as sess:
        r = await sess.get(
            f"{settings.deribit_rest}/public/get_instruments",
            params=dict(currency=settings.currency, kind="option", expired="false"),
        )
        data = (await r.json())["result"]
        # placeholder filter (refined later in processor)
        return [d["instrument_name"] for d in data]


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
    token, token_exp = await auth_token()

    while True:
        if time.time() > token_exp:
            token, token_exp = await auth_token()

        instruments = await current_instruments()
        spot_ch = f"deribit_price_index.{settings.currency.lower()}_usd"
        subs = (
            [spot_ch]
            + [f"ticker.{inst}.100ms" for inst in instruments]
            + [f"book.{inst}.100ms" for inst in instruments]
        )

        hdrs = {"Authorization": f"Bearer {token}"}
        async with websockets.connect(settings.deribit_ws, extra_headers=hdrs, ping_interval=20) as ws:
            await subscribe(ws, subs)
            async for msg in ws:
                await redis.xadd(STREAM_KEY_RAW, {"d": msg})