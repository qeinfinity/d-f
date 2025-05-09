# dealer_flow/processor.py
import asyncio, time, orjson, pandas as pd, numpy as np, sys
import re, datetime as dt, calendar
import logging
from collections import deque, defaultdict

import aioredis # <--- Ensure aioredis.exceptions can be caught

from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW, STREAM_KEY_METRICS
from dealer_flow.gamma_flip import gamma_flip_distance
from dealer_flow.vanna_charm_volga import roll_up
from dealer_flow.hpp_score import hpp
from dealer_flow.rules import classify
from dealer_flow.dealer_net import infer_dealer_net
from dealer_flow.greek_calc import greeks as bs_greeks

LOG_STORE_THRESHOLD = 5

JSON_OPTS = orjson.OPT_SERIALIZE_NUMPY
GROUP, CONSUMER = "processor", "p1"
BLOCK_MS = 200
ROLL_FREQ = 1.0
_DATE_RE = re.compile(r"(\d{1,2})([A-Z]{3})(\d{2})")

if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s:%(lineno)d %(message)s")
logger = logging.getLogger(__name__)

spot = [0.0]
last_pub_price = [0.0]
greek_store = {}
gamma_by_strike = {} # Note: This global one isn't updated in the latest logic; current_gamma_by_strike is local to maybe_publish
prices = deque(maxlen=1)
tick_times = deque(maxlen=1000)


async def wait_for_redis(redis_client, retries=10, delay_seconds=3): # Increased retries/delay
    logger.info(f"Waiting for Redis to become available (max {retries} retries)...")
    for i in range(retries):
        try:
            await redis_client.ping()
            logger.info("Redis is ready and responding to PING.")
            return True
        except aioredis.exceptions.BusyLoadingError as e:
            logger.warning(f"Redis is busy loading (attempt {i+1}/{retries}): {e}. Retrying in {delay_seconds}s...")
            await asyncio.sleep(delay_seconds)
        except (aioredis.exceptions.ConnectionError, ConnectionRefusedError) as e: # Added ConnectionRefusedError
            logger.warning(f"Redis connection error (attempt {i+1}/{retries}): {e}. Retrying in {delay_seconds}s...")
            await asyncio.sleep(delay_seconds)
        except Exception as e: # Catch any other unexpected errors during ping
            logger.error(f"Unexpected error while waiting for Redis (attempt {i+1}/{retries}): {e}. Retrying in {delay_seconds}s...", exc_info=True)
            await asyncio.sleep(delay_seconds)
    logger.error(f"Redis not ready after {retries} retries. Processor might fail to connect or operate correctly.")
    return False

async def ensure_group(r):
    try:
        await r.xgroup_create(STREAM_KEY_RAW, GROUP, id="$", mkstream=True)
        logger.info(f"Successfully created Redis stream group '{GROUP}' for stream '{STREAM_KEY_RAW}'.")
    except Exception as e: # Catching generic Exception is okay here if specific error string is checked
        # The error string for "group already exists" in Redis is "BUSYGROUP Consumer Group name already exists"
        if "BUSYGROUP" in str(e).upper(): # Make check case-insensitive
            logger.info(f"Redis stream group '{GROUP}' already exists for stream '{STREAM_KEY_RAW}'.")
        else:
            # Log other errors but don't necessarily re-raise if non-critical for group creation
            logger.warning(f"Could not create or verify Redis stream group '{GROUP}' (may be non-critical if group exists): {e}")


async def maybe_publish(redis):
    # ... (existing maybe_publish logic from your last confirmed working version or my last good patch)
    # For brevity, assuming the last version of maybe_publish is here.
    # Key parts:
    now = time.time()
    while tick_times and now - tick_times[0] > 1.0:
        tick_times.popleft()

    current_spot_for_payload = spot[0]
    if current_spot_for_payload <= 0:
        return

    if not greek_store:
        return
        
    df = pd.DataFrame.from_dict(greek_store, orient="index")
    if df.empty:
        return

    dealer = infer_dealer_net(df.reset_index(names="instrument"))
    signed = dealer.copy()
    greeks_to_sign = ["gamma", "vanna", "charm", "volga"]
    
    for greek_col in greeks_to_sign:
        if greek_col not in signed.columns:
            signed[greek_col] = 0.0 
            
    signed[greeks_to_sign] = signed[greeks_to_sign].mul(signed["dealer_side_mult"], axis=0)
    current_gamma_by_strike = signed.groupby("strike")["gamma"].sum() if "strike" in signed.columns and "gamma" in signed.columns else pd.Series(dtype='float64')


    agg = roll_up(signed) 
    flip = gamma_flip_distance(current_gamma_by_strike, current_spot_for_payload)

    if last_pub_price[0] <= 0 and current_spot_for_payload > 0:
        last_pub_price[0] = current_spot_for_payload

    spot_move_sign = 0
    if last_pub_price[0] > 0:
        if current_spot_for_payload > last_pub_price[0]: spot_move_sign = 1
        elif current_spot_for_payload < last_pub_price[0]: spot_move_sign = -1
    
    HPP_val = hpp(spot_move_sign, agg.get("NGI", 0.0), agg.get("VSS", 0.0), agg.get("CHL_24h", 0.0))
    
    spot_change_pct = 0.0
    if last_pub_price[0] > 0:
        spot_change_pct = (current_spot_for_payload / last_pub_price[0]) - 1.0

    flow_for_classify = {
        "NGI": agg.get("NGI", 0.0), "VSS": agg.get("VSS", 0.0),
        "CHL_24h": agg.get("CHL_24h", 0.0), "HPP": HPP_val
    }
    total_notional_usd = signed["notional_usd"].sum() if "notional_usd" in signed and not signed["notional_usd"].empty else 1.0
    adv_usd_placeholder = total_notional_usd * 0.001 if total_notional_usd > 0 else 1.0 

    scenario = classify(flow_for_classify, adv_usd=adv_usd_placeholder, spot_change_pct=spot_change_pct)
    last_pub_price[0] = current_spot_for_payload

    payload = {
        "ts": now, "price": current_spot_for_payload, "msg_rate": len(tick_times),
        **agg, "flip_pct": flip, "HPP": HPP_val, "scenario": scenario,
    }
    await redis.xadd(
        STREAM_KEY_METRICS,
        {"d": orjson.dumps(payload, option=JSON_OPTS)}
    )
    logger.debug(f"Published metrics: Price={current_spot_for_payload:.2f}, NGI={agg.get('NGI',0):.4f}, VSS={agg.get('VSS',0):.4f}")


def _expiry_ts(sym: str) -> float:
    # ... (existing _expiry_ts logic)
    date_part = sym.split("-")[1]
    m = _DATE_RE.fullmatch(date_part)
    if not m: raise ValueError(f"unparsable date {date_part}")
    day, mon, yy = int(m[1]), m[2], int(m[3])
    month_num = dt.datetime.strptime(mon, "%b").month
    year_full = 2000 + yy
    dt_exp = dt.datetime(year_full, month_num, day, 8, tzinfo=dt.timezone.utc)
    return dt_exp.timestamp()


async def processor():
    redis_connection = await get_redis() # Get the connection object
    
    # Wait for Redis to be ready before proceeding
    if not await wait_for_redis(redis_connection):
        logger.critical("Processor cannot start: Redis not available after retries.")
        return # Exit if Redis is not ready

    try:
        await ensure_group(redis_connection) # Pass the connection object
    except Exception as e:
        logger.error(f"Failed to ensure Redis group, processor may not work correctly: {e}", exc_info=True)
        # Decide if this is critical enough to stop the processor
        # For now, we'll let it try to continue, as xreadgroup might still work if group exists.

    logger.info("PROCESSOR: started, waiting for data …")
    last_pub = time.time()

    while True:
        try:
            # Pass the connection object to xreadgroup
            resp = await redis_connection.xreadgroup(GROUP, CONSUMER, streams={STREAM_KEY_RAW: ">"}, count=500, block=BLOCK_MS)
            if resp:
                for _, msgs in resp:
                    for mid, data_dict in msgs:
                        # ... (the rest of your existing processing loop for messages)
                        # For brevity, assuming the message processing logic is here.
                        # Key part from your latest working/patched version:
                        try:
                            raw_msg_data = data_dict.get(b"d")
                            if not raw_msg_data: continue
                            
                            j = orjson.loads(raw_msg_data)
                            params = j.get("params", {})
                            ch = params.get("channel")
                            msg_payload = params.get("data")

                            if not isinstance(msg_payload, dict) or not ch: continue
                            
                            if ch.lower().startswith("deribit_price_index"):
                                current_spot_price = float(msg_payload.get("price") or msg_payload.get("index_price") or 0.0)
                                if current_spot_price > 0: spot[0] = current_spot_price
                                continue 

                            if ch.startswith("ticker."):
                                mark_price = float(msg_payload.get("mark_price", 0.0))
                                inst = msg_payload.get("instrument_name")
                                if not inst: continue
                                
                                strike_str = inst.split("-")[2] if len(inst.split("-")) > 2 else None
                                if not strike_str: continue
                                strike = float(strike_str)

                                try: expiry_ts = _expiry_ts(inst)
                                except ValueError: continue

                                now_ts = msg_payload.get("timestamp", time.time() * 1000) / 1000
                                T = max((expiry_ts - now_ts), 0.0) / (365 * 24 * 3600)
                                
                                open_interest = msg_payload.get("open_interest", 0.0)
                                current_underlying_price = spot[0] or mark_price 
                                notional = open_interest * current_underlying_price if current_underlying_price > 0 else 0.0

                                deriv_greeks = msg_payload.get("greeks", {})
                                gamma_deribit = deriv_greeks.get("gamma") 
                                vanna_deribit = deriv_greeks.get("vanna")
                                charm_deribit = deriv_greeks.get("charm")
                                volga_deribit = deriv_greeks.get("volga")

                                gamma = float(gamma_deribit) if gamma_deribit is not None else None
                                vanna = float(vanna_deribit) if vanna_deribit is not None else None
                                charm = float(charm_deribit) if charm_deribit is not None else None
                                volga = float(volga_deribit) if volga_deribit is not None else None
                                
                                sigma = msg_payload.get("mark_iv", 0.0) / 100.0
                                can_calc_bs = sigma > 0 and T > 0 and current_underlying_price > 0
                                calculated_gamma_bs = None

                                if can_calc_bs:
                                    S_param_bs = np.array([current_underlying_price])
                                    K_param_bs = np.array([strike])
                                    option_type_bs = 1 if "-C-" in inst else (0 if "-P-" in inst else 1)
                                    
                                    _g_calc, v_calc, c_calc, vg_calc = bs_greeks(
                                        S_param_bs, K_param_bs, np.array([T]),
                                        0.0, np.array([sigma]), np.array([option_type_bs])
                                    )
                                    
                                    calculated_gamma_bs = float(_g_calc[0]) if not np.isnan(_g_calc[0]) else 0.0
                                    gamma = calculated_gamma_bs 

                                    if vanna is None: vanna = float(v_calc[0]) if not np.isnan(v_calc[0]) else 0.0
                                    if charm is None: charm = float(c_calc[0]) if not np.isnan(c_calc[0]) else 0.0
                                    if volga is None: volga = float(vg_calc[0]) if not np.isnan(vg_calc[0]) else 0.0
                                else: 
                                    if gamma is None: gamma = 0.0
                                    if vanna is None: vanna = 0.0
                                    if charm is None: charm = 0.0
                                    if volga is None: volga = 0.0
                                
                                gamma = gamma if gamma is not None else 0.0
                                vanna = vanna if vanna is not None else 0.0
                                charm = charm if charm is not None else 0.0
                                volga = volga if volga is not None else 0.0

                                # logger.info(...) # Your detailed GREEK_PROCESSING log

                                final_greeks_payload = {
                                    "gamma": gamma, "vanna": vanna, "charm": charm, "volga": volga,
                                    "notional_usd": notional, "strike": strike,
                                }
                                greek_store[inst] = final_greeks_payload
                                
                                if len(greek_store) % LOG_STORE_THRESHOLD == 0 and len(greek_store) > 0:
                                    logger.info(f"PROCESSOR: Stored greeks for {len(greek_store)} instruments. Latest: {inst}")
                            
                            tick_times.append(time.time())

                        except Exception as e:
                            failing_message_id = mid.decode() if isinstance(mid, bytes) else str(mid)
                            logger.error(f"PROCESSOR MSG PARSE ERR (msg_id: {failing_message_id}): {e} -- Failing Msg: {str(raw_msg_data)[:200]}", exc_info=False) # Keep exc_info False or True based on verbosity preference

            current_loop_time = time.time()
            if current_loop_time - last_pub >= ROLL_FREQ:
                await maybe_publish(redis_connection) # Pass the connection object
                last_pub = current_loop_time
        
        except aioredis.exceptions.BusyLoadingError as e:
            logger.warning(f"Redis is busy loading during XREADGROUP: {e}. Sleeping and retrying...")
            await asyncio.sleep(5) # Sleep for a bit before retrying the main loop
        except (aioredis.exceptions.ConnectionError, ConnectionRefusedError) as e:
            logger.error(f"Redis connection error during XREADGROUP: {e}. Attempting to reconnect/retry...", exc_info=True)
            await asyncio.sleep(5) # Wait before trying to reconnect or retry
            # Potentially re-initialize redis_connection if necessary, though aioredis handles some reconnects.
            # For a robust solution, you might need a loop here to re-establish `redis_connection = await get_redis()`
            # and then `await wait_for_redis(redis_connection)`.
            # For now, just sleeping and letting the outer loop retry.
            redis_connection = await get_redis() # Re-establish connection
            if not await wait_for_redis(redis_connection):
                 logger.critical("Lost Redis connection and could not re-establish. Processor stopping.")
                 break # Exit main while loop
            await ensure_group(redis_connection) # Re-ensure group after reconnect
            logger.info("Re-established Redis connection and ensured group.")

        except Exception as e:
            logger.error(f"Unhandled error in processor main loop: {e}", exc_info=True)
            await asyncio.sleep(5) # Prevent rapid crashing loops

if __name__ == "__main__":
    try:
        asyncio.run(processor())
    except KeyboardInterrupt:
        logger.info("Processor interrupted by user.")
    except Exception as e: # Catch any exception that might occur during asyncio.run itself
        logger.critical(f"Processor asyncio.run() crashed: {e}", exc_info=True)

