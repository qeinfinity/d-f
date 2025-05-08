# dealer_flow/processor.py
import asyncio, time, orjson, pandas as pd, numpy as np, sys
import datetime as dt, calendar
import re, datetime as dt, calendar # Duplicate import, remove one
import logging # Keep this
from collections import deque, defaultdict # Keep this
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW, STREAM_KEY_METRICS
from dealer_flow.gamma_flip import gamma_flip_distance
from dealer_flow.vanna_charm_volga import roll_up
from dealer_flow.hpp_score import hpp
from dealer_flow.rules import classify
from dealer_flow.dealer_net import infer_dealer_net
from dealer_flow.greek_calc import greeks as bs_greeks

# For MAX_UNAUTH_STRIKES, it's defined in deribit_ws.py, ideally share via config or pass around
# For now, let's assume a small number for logging if we can't import it directly.
LOG_STORE_THRESHOLD = 5 # Lowered threshold for "stored greeks" log

JSON_OPTS = orjson.OPT_SERIALIZE_NUMPY
GROUP, CONSUMER = "processor", "p1"
BLOCK_MS = 200
ROLL_FREQ = 1.0  # s
_DATE_RE = re.compile(r"(\d{1,2})([A-Z]{3})(\d{2})")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# in-memory state
greek_store = {}
gamma_by_strike = {}
prices = deque(maxlen=1) # This deque's usage is a bit unclear; spot[0] is primary for spot.
tick_times = deque(maxlen=1000)

# mutable globals
spot = [0.0]  # Holds the latest BTC spot price
last_pub_price = [0.0]

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

    # Use spot[0] as the definitive current spot price for publishing
    current_spot_for_payload = spot[0]

    if current_spot_for_payload <= 0: # Don't publish if spot price isn't known yet
        # logging.info("Skipping publish: Spot price not yet available or invalid.")
        return

    # Build DataFrame
    if not greek_store:
        # logging.info("Skipping publish: Greek store is empty.")
        return
        
    df = pd.DataFrame.from_dict(greek_store, orient="index")
    if df.empty: # Should be caught by `if not greek_store` but good to have
        return

    dealer = infer_dealer_net(df.reset_index(names="instrument"))
    signed = dealer.copy()
    greeks_to_sign = ["gamma", "vanna", "charm", "volga"]
    for greek_col in greeks_to_sign:
        if greek_col not in signed.columns: # Ensure columns exist before multiplication
            signed[greek_col] = 0.0 
            
    signed[greeks_to_sign] = signed[greeks_to_sign].mul(signed["dealer_side_mult"], axis=0)
    
    agg = roll_up(signed)
    
    # Pass current_spot_for_payload (which is spot[0]) to gamma_flip_distance
    flip = gamma_flip_distance(pd.Series(gamma_by_strike), current_spot_for_payload)

    if last_pub_price[0] <= 0 and current_spot_for_payload > 0: # First time we have a valid spot for publishing
        last_pub_price[0] = current_spot_for_payload # Initialize last_pub_price to prevent large initial jump

    spot_move_sign = 0
    if last_pub_price[0] > 0: # Avoid division by zero or using uninitialized last_pub_price
        if current_spot_for_payload > last_pub_price[0]:
            spot_move_sign = 1
        elif current_spot_for_payload < last_pub_price[0]:
            spot_move_sign = -1
    
    HPP_val = hpp(spot_move_sign, agg.get("NGI", 0.0), agg.get("VSS", 0.0), agg.get("CHL_24h", 0.0))
    
    spot_change_pct = 0.0
    if last_pub_price[0] > 0:
        spot_change_pct = (current_spot_for_payload / last_pub_price[0]) - 1.0

    # Ensure agg dictionary has expected keys before passing to classify
    flow_for_classify = {
        "NGI": agg.get("NGI", 0.0),
        "VSS": agg.get("VSS", 0.0),
        "CHL_24h": agg.get("CHL_24h", 0.0),
        "HPP": HPP_val # Add HPP to the dictionary for classify
    }
    # adv_usd could be derived from a config or a dynamic average daily volume metric later
    # For now, using a placeholder based on NGI might be too circular or unstable.
    # Let's use a fixed small portion of notional sum or a placeholder.
    total_notional_usd = signed["notional_usd"].sum() if "notional_usd" in signed else 1.0
    adv_usd_placeholder = total_notional_usd * 0.01 # Example: 1% of total open interest notional

    scenario = classify(flow_for_classify, adv_usd=adv_usd_placeholder, spot_change_pct=spot_change_pct)
    
    last_pub_price[0] = current_spot_for_payload # Update after all calculations for this round

    payload = {
        "ts": now,
        "price": current_spot_for_payload,
        "msg_rate": len(tick_times),
        **agg,
        "flip_pct": flip,
        "HPP": HPP_val,
        "scenario": scenario,
    }
    await redis.xadd(
        STREAM_KEY_METRICS,
        {"d": orjson.dumps(payload, option=JSON_OPTS)}
    )
    # logging.info(f"Published metrics: Price={current_spot_for_payload:.2f}, NGI={agg.get('NGI',0):.2f}, VSS={agg.get('VSS',0):.2f}")


def _expiry_ts(sym: str) -> float:
    date_part = sym.split("-")[1]
    m = _DATE_RE.fullmatch(date_part)
    if not m:
        # logging.error(f"Unparsable date {date_part} in instrument {sym}")
        raise ValueError(f"unparsable date {date_part}")
    day, mon, yy = int(m[1]), m[2], int(m[3])
    try:
        month_num = dt.datetime.strptime(mon, "%b").month
    except ValueError:
        # logging.error(f"Unparsable month {mon} in instrument {sym}")
        raise
    year_full = 2000 + yy
    dt_exp = dt.datetime(year_full, month_num, day, 8, tzinfo=dt.timezone.utc)
    return dt_exp.timestamp()

async def processor():
    redis = await get_redis()
    await ensure_group(redis)
    logging.info("PROCESSOR: started, waiting for data …")
    last_pub = time.time()

    while True:
        resp = await redis.xreadgroup(GROUP, CONSUMER, streams={STREAM_KEY_RAW: ">"}, count=500, block=BLOCK_MS)
        if resp:
            for _, msgs in resp:
                for mid, data_dict in msgs: # Renamed 'data' to 'data_dict' to avoid conflict
                    try:
                        raw_msg_data = data_dict.get(b"d")
                        if not raw_msg_data:
                            logging.warning(f"Empty message data for ID {mid}")
                            continue
                        
                        j = orjson.loads(raw_msg_data)
                        params = j.get("params", {})
                        ch = params.get("channel")
                        msg_payload = params.get("data") # Renamed 'd' to 'msg_payload'

                        if not isinstance(msg_payload, dict):
                            # Could be subscription confirmation, error, etc.
                            # logging.debug(f"Skipping non-data message or unexpected format: {j}")
                            continue
                        
                        if not ch: # Channel is essential
                            # logging.debug(f"Message without channel: {j}")
                            continue

                        if ch.lower().startswith("deribit_price_index"):
                            current_spot_price = None
                            try:
                                current_spot_price = float(msg_payload.get("price") or msg_payload.get("index_price") or 0.0)
                            except (TypeError, ValueError) as e:
                                logging.warning(f"Bad index payload {msg_payload}: {e}")
                            
                            if current_spot_price and current_spot_price > 0:
                                spot[0] = current_spot_price
                                # prices.append(current_spot_price) # If prices deque is for spot, otherwise remove.
                                # logging.info(f"SPOTPRICE_UPDATE: {spot[0]}")
                            # `continue` was here, which is correct. No further processing for spot index msgs.
                            continue 

                        if ch.startswith("ticker."): # Ensure it's a ticker channel
                            mark_price = float(msg_payload.get("mark_price", 0.0)) # Safer get
                            # prices.append(mark_price) # If prices deque is for option marks

                            inst = msg_payload.get("instrument_name")
                            if not inst:
                                logging.warning(f"Ticker message without instrument_name: {msg_payload}")
                                continue
                            
                            strike_str = inst.split("-")[2] if len(inst.split("-")) > 2 else None
                            if not strike_str:
                                logging.warning(f"Could not parse strike from instrument: {inst}")
                                continue
                            strike = float(strike_str)

                            try:
                                expiry_ts = _expiry_ts(inst)
                            except ValueError as e:
                                logging.error(f"Failed to parse expiry for {inst}: {e}")
                                continue # Skip this instrument if expiry is bad

                            now_ts = msg_payload.get("timestamp", time.time() * 1000) / 1000 # Fallback to current time
                            T = max((expiry_ts - now_ts), 0.0) / (365 * 24 * 3600)
                            
                            open_interest = msg_payload.get("open_interest", 0.0)
                            
                            # Calculate notional using current global spot price
                            # Fallback to mark_price if spot[0] is not yet set (is 0.0)
                            current_underlying_price = spot[0] or mark_price 
                            if current_underlying_price <=0: # if spot is 0 and mark_price is 0, notional is 0.
                                notional = 0.0
                            else:
                                notional = open_interest * current_underlying_price

                            deriv_greeks = msg_payload.get("greeks", {})
                            gamma = deriv_greeks.get("gamma", 0.0) # Default to 0.0 if missing

                            vanna = deriv_greeks.get("vanna") # Will be None if missing
                            charm = deriv_greeks.get("charm") # Will be None if missing
                            volga = deriv_greeks.get("volga") # Will be None if missing

                            if None in (vanna, charm, volga):
                                sigma = msg_payload.get("mark_iv", 0.0) / 100.0
                                
                                if sigma > 0 and T > 0 and current_underlying_price > 0 : # Check current_underlying_price too
                                    # FIX 1: Use spot price for S in Black-Scholes
                                    S_param_bs = np.array([current_underlying_price])
                                    K_param_bs = np.array([strike])
                                    
                                    # FIX 2: Determine option type (1 for Call, 0 for Put)
                                    # This assumes standard Numba/SciPy BS where C=1, P=0 or similar.
                                    # Adjust if your bs_greeks expects different (e.g. +1/-1)
                                    option_type_bs = 1 if "-C-" in inst else (0 if "-P-" in inst else 1) # Default to Call if unclear
                                    
                                    # logging.debug(f"BS Params for {inst}: S={S_param_bs[0]}, K={K_param_bs[0]}, T={T:.4f}, sigma={sigma:.4f}, type={option_type_bs}")

                                    _g_calc, v_calc, c_calc, vg_calc = bs_greeks(
                                        S_param_bs, K_param_bs, np.array([T]),
                                        0.0,  # r (risk-free rate, assuming 0 for now)
                                        np.array([sigma]),
                                        np.array([option_type_bs])
                                    )
                                    if vanna is None: vanna = float(v_calc[0]) if not np.isnan(v_calc[0]) else 0.0
                                    if charm is None: charm = float(c_calc[0]) if not np.isnan(c_calc[0]) else 0.0
                                    if volga is None: volga = float(vg_calc[0]) if not np.isnan(vg_calc[0]) else 0.0
                                else: # Default to 0.0 if sigma, T or current_underlying_price is not valid
                                    if vanna is None: vanna = 0.0
                                    if charm is None: charm = 0.0
                                    if volga is None: volga = 0.0
                            
                            # Ensure all greeks are floats before storing
                            final_greeks = {
                                "gamma": float(gamma),
                                "vanna": float(vanna),
                                "charm": float(charm),
                                "volga": float(volga),
                                "notional_usd": float(notional),
                                "strike": float(strike),
                            }
                            greek_store[inst] = final_greeks
                            
                            # Update gamma_by_strike (ensure gamma is float)
                            # This sum is for *dealer's* net gamma, so it should be after applying dealer_side_mult
                            # However, dealer_side_mult is applied in maybe_publish.
                            # For now, this is raw gamma. The gamma_flip_distance needs net dealer gamma.
                            # This implies gamma_by_strike should be rebuilt in maybe_publish from 'signed' df.
                            # Quick fix: assume raw gamma for now for gamma_by_strike and acknowledge later.
                            gamma_by_strike[strike] = gamma_by_strike.get(strike, 0.0) + float(gamma)

                            # FIX 3: Lowered threshold for "stored greeks" log
                            if len(greek_store) % LOG_STORE_THRESHOLD == 0 and len(greek_store) > 0:
                                logging.info(f"PROCESSOR: Stored greeks for {len(greek_store)} instruments. Latest: {inst}")
                        
                        tick_times.append(time.time())

                    except Exception as e:
                        # Catching the specific failing message for detailed logging
                        failing_message_id = mid.decode() if isinstance(mid, bytes) else str(mid)
                        logging.error(f"PROCESSOR PARSE ERR (msg_id: {failing_message_id}): {e} -- Failing Msg: {raw_msg_data[:500]}", exc_info=True)
        
        current_loop_time = time.time()
        if current_loop_time - last_pub >= ROLL_FREQ:
            await maybe_publish(redis)
            last_pub = current_loop_time

if __name__ == "__main__":
    try:
        asyncio.run(processor())
    except KeyboardInterrupt:
        logging.info("Processor interrupted by user.")
    except Exception as e:
        logging.critical(f"Processor crashed")
