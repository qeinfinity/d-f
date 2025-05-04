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

"""
Processor: aggregates option greeks & dealer net,
publishes roll-ups every second to `dealer_metrics`.
"""
import asyncio, time, orjson, pandas as pd, numpy as np, sys
import datetime as dt, calendar
from collections import deque, defaultdict
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW, STREAM_KEY_METRICS
from dealer_flow.gamma_flip import gamma_flip_distance
from dealer_flow.vanna_charm_volga import roll_up
from dealer_flow.dealer_net import infer_dealer_net
from dealer_flow.greek_calc import greeks as bs_greeks   # NEW

GROUP, CONSUMER = "processor", "p1"
BLOCK_MS = 200
ROLL_FREQ = 1.0  # s

# in-memory state
greek_store = {}        # inst -> dict(gamma, vanna, charm, volga, OI)
gamma_by_strike = {}    # strike -> net dealer gamma
prices = deque(maxlen=1)
tick_times = deque(maxlen=1000)

async def ensure_group(r):
    try:
        await r.xgroup_create(STREAM_KEY_RAW, GROUP, id="$", mkstream=True)
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            raise

async def maybe_publish(redis):
    now = time.time()
    while tick_times and now - tick_times[0] > 1.0:
        tick_times.popleft()
    if not prices:
        return
    # Build DataFrame
    df = pd.DataFrame.from_dict(greek_store, orient="index")
    if df.empty:
        return
    dealer = infer_dealer_net(df.reset_index(names="instrument"))
    agg = roll_up(dealer)
    flip = gamma_flip_distance(pd.Series(gamma_by_strike), prices[-1])
    payload = {"ts": now, "price": prices[-1], "msg_rate": len(tick_times), **agg, "flip_pct": flip}
    await redis.xadd(STREAM_KEY_METRICS, {"d": orjson.dumps(payload)})

def _expiry_ts(sym: str) -> float:
    # sym like BTC-24MAY25-60000-P
    day = int(sym[4:6])
    mon = sym[6:9]           # MAY
    year = int(sym[9:11])    # 25 (=> 2025)
    month_num = dt.datetime.strptime(mon, "%b").month
    year_full = 2000 + year
    return calendar.timegm(dt.datetime(year_full, month_num, day, 8).timetuple())

async def processor():
    redis = await get_redis()
    await ensure_group(redis)
    print("PROCESSOR: started, waiting for data …", file=sys.stderr)
    last_pub = time.time()

    while True:
        resp = await redis.xreadgroup(GROUP, CONSUMER, streams={STREAM_KEY_RAW: ">"}, count=500, block=BLOCK_MS)
        if resp:
            for _, msgs in resp:
                for mid, data in msgs:
                    try:
                        j = orjson.loads(data[b"d"])
                        params = j.get("params", {})
                        ch, d = params.get("channel"), params.get("data")
                        if not isinstance(d, dict):
                            continue
                        if ch.startswith("ticker"):
                            mark = float(d["mark_price"])
                            prices.append(mark)

                            inst = d["instrument_name"]      # BTC-24MAY25-60000-P
                            strike = float(inst.split("-")[2])
                            expiry_ts = _expiry_ts(inst) 
                            now_ts    = d["timestamp"] / 1000
                            T = max((expiry_ts - now_ts), 0.0) / (365 * 24 * 3600)

                            size  = d["open_interest"]        # contracts
                            notional = size * mark

                            deriv_greeks = d.get("greeks", {})
                            gamma = deriv_greeks.get("gamma", 0.0)

                            # If vanna/charm/volga missing → compute
                            vanna  = deriv_greeks.get("vanna")
                            charm  = deriv_greeks.get("charm")
                            volga  = deriv_greeks.get("volga")

                            if None in (vanna, charm, volga):
                                sigma = d.get("mark_iv", 0) / 100  # iv in pct
                                if sigma <= 0 or T <= 0:
                                    # cannot compute, default zeros
                                    vanna = vanna or 0.0
                                    charm = charm or 0.0
                                    volga = volga or 0.0
                                else:
                                    S = np.array([mark])
                                    K = np.array([strike])
                                    g, v, c, vg = bs_greeks(
                                        S, K, np.array([T]), 0.0, np.array([sigma]), np.array([1])
                                    )
                                    vanna = vanna or float(v[0])
                                    charm = charm or float(c[0])
                                    volga = volga or float(vg[0])

                            greeks = {
                                "gamma": gamma,
                                "vanna": vanna,
                                "charm": charm,
                                "volga": volga,
                                "notional_usd": notional,
                                "strike": strike,
                            }
                            greek_store[inst] = greeks
                            gamma_by_strike[strike] = (
                                gamma_by_strike.get(strike, 0.0) + gamma
                            )
                            if len(greek_store) % 1000 == 0:
                                print(f"PROCESSOR: stored {len(greek_store)} greeks",
                                      file=sys.stderr)
                        tick_times.append(time.time())
                    except Exception as e:
                        print(f"PARSE ERR {e}", file=sys.stderr)
        now = time.time()
        if now - last_pub >= ROLL_FREQ:
            await maybe_publish(redis)
            last_pub = now

if __name__ == "__main__":
    asyncio.run(processor())
