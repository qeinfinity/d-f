# dealer_flow/processor.py
import asyncio, time, orjson, pandas as pd, numpy as np, sys
# import datetime as dt, calendar # Already imported below
import re, datetime as dt, calendar
import logging
from collections import deque, defaultdict
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW, STREAM_KEY_METRICS
from dealer_flow.gamma_flip import gamma_flip_distance
from dealer_flow.vanna_charm_volga import roll_up
from dealer_flow.hpp_score import hpp
from dealer_flow.rules import classify
from dealer_flow.dealer_net import infer_dealer_net
from dealer_flow.greek_calc import greeks as bs_greeks

LOG_STORE_THRESHOLD = 5 # Keep lowered threshold

JSON_OPTS = orjson.OPT_SERIALIZE_NUMPY
GROUP, CONSUMER = "processor", "p1"
BLOCK_MS = 200
ROLL_FREQ = 1.0  # s
_DATE_RE = re.compile(r"(\d{1,2})([A-Z]{3})(\d{2})")

# Ensure logging is configured (it was, just confirming)
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s:%(lineno)d %(message)s")
logger = logging.getLogger(__name__) # Use a specific logger

# in-memory state
greek_store = {}
gamma_by_strike = {} # This will store the sum of FINAL gammas per strike
prices = deque(maxlen=1) 
tick_times = deque(maxlen=1000)

spot = [0.0]
last_pub_price = [0.0]

async def ensure_group(r):
    try:
        await r.xgroup_create(STREAM_KEY_RAW, GROUP, id="$", mkstream=True)
    except Exception as e:
        if "BUSYGROUP" not in str(e): # Make sure this matches Redis error string
            logger.info(f"Stream group {GROUP} already exists or other non-critical error: {e}")
        # else: # Re-raise if it's a critical error other than BUSYGROUP
            # raise # Commented out to prevent crash on other Redis issues during dev

async def maybe_publish(redis):
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
            signed[greek_col] = 0.0 # Ensure column exists
            logger.warning(f"Greek column {greek_col} was missing from DataFrame before signing. Defaulted to 0.")
            
    signed[greeks_to_sign] = signed[greeks_to_sign].mul(signed["dealer_side_mult"], axis=0)
    
    # Rebuild gamma_by_strike using the potentially signed gamma values from the DataFrame
    # This ensures gamma_flip_distance uses dealer-netted gamma if side info is available.
    current_gamma_by_strike = signed.groupby("strike")["gamma"].sum()

    agg = roll_up(signed) # roll_up should use the 'signed' greeks
    
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
    adv_usd_placeholder = total_notional_usd * 0.01 if total_notional_usd > 0 else 1.0 # Avoid 0

    scenario = classify(flow_for_classify, adv_usd=adv_usd_placeholder, spot_change_pct=spot_change_pct)
    last_pub_price[0] = current_spot_for_payload

    payload = {
        "ts": now, "price": current_spot_for_payload, "msg_rate": len(tick_times),
        **agg, "flip_pct": flip, "HPP": HPP_val, "scenario": scenario,
    }
    await redis.xadd(STREAM_KEY_METRICS, {"d": orjson.dumps(payload, option=JSON_OPTS)})
    logger.debug(f"Published metrics: Price={current_spot_for_payload:.2f}, NGI={agg.get('NGI',0):.4f}, VSS={agg.get('VSS',0):.4f}")

def _expiry_ts(sym: str) -> float:
    date_part = sym.split("-")[1]
    m = _DATE_RE.fullmatch(date_part)
    if not m: raise ValueError(f"unparsable date {date_part}")
    day, mon, yy = int(m[1]), m[2], int(m[3])
    month_num = dt.datetime.strptime(mon, "%b").month
    year_full = 2000 + yy
    dt_exp = dt.datetime(year_full, month_num, day, 8, tzinfo=dt.timezone.utc)
    return dt_exp.timestamp()

async def processor():
    redis = await get_redis()
    await ensure_group(redis)
    logger.info("PROCESSOR: started, waiting for data …")
    last_pub = time.time()

    while True:
        resp = await redis.xreadgroup(GROUP, CONSUMER, streams={STREAM_KEY_RAW: ">"}, count=500, block=BLOCK_MS)
        if resp:
            for _, msgs in resp:
                for mid, data_dict in msgs:
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
                            gamma_deribit = deriv_greeks.get("gamma") # Can be None
                            vanna_deribit = deriv_greeks.get("vanna")
                            charm_deribit = deriv_greeks.get("charm")
                            volga_deribit = deriv_greeks.get("volga")

                            # Initialize with Deribit values if they exist, else None
                            gamma = float(gamma_deribit) if gamma_deribit is not None else None
                            vanna = float(vanna_deribit) if vanna_deribit is not None else None
                            charm = float(charm_deribit) if charm_deribit is not None else None
                            volga = float(volga_deribit) if volga_deribit is not None else None
                            
                            sigma = msg_payload.get("mark_iv", 0.0) / 100.0
                            can_calc_bs = sigma > 0 and T > 0 and current_underlying_price > 0

                            calculated_gamma_bs = None # For logging

                            if can_calc_bs:
                                S_param_bs = np.array([current_underlying_price])
                                K_param_bs = np.array([strike])
                                option_type_bs = 1 if "-C-" in inst else (0 if "-P-" in inst else 1)
                                
                                _g_calc, v_calc, c_calc, vg_calc = bs_greeks(
                                    S_param_bs, K_param_bs, np.array([T]),
                                    0.0, np.array([sigma]), np.array([option_type_bs])
                                )
                                
                                calculated_gamma_bs = float(_g_calc[0]) if not np.isnan(_g_calc[0]) else 0.0
                                gamma = calculated_gamma_bs # PRIORITIZE BS GAMMA

                                if vanna is None: vanna = float(v_calc[0]) if not np.isnan(v_calc[0]) else 0.0
                                if charm is None: charm = float(c_calc[0]) if not np.isnan(c_calc[0]) else 0.0
                                if volga is None: volga = float(vg_calc[0]) if not np.isnan(vg_calc[0]) else 0.0
                            else:
                                # If BS cannot be calculated, ensure Nones (including gamma if it was None) become 0.0
                                if gamma is None: gamma = 0.0
                                if vanna is None: vanna = 0.0
                                if charm is None: charm = 0.0
                                if volga is None: volga = 0.0
                            
                            # Final safety net: if anything is still None, make it 0.0
                            gamma = gamma if gamma is not None else 0.0
                            vanna = vanna if vanna is not None else 0.0
                            charm = charm if charm is not None else 0.0
                            volga = volga if volga is not None else 0.0

                            logger.info(
                                f"GREEK_PROCESSING: Inst={inst}, Spot={current_underlying_price:.2f}, T={T:.4f}, IV={sigma:.4f}, OI={open_interest}, "
                                f"DeribitGamma={gamma_deribit}, CanCalcBS={can_calc_bs}, BSGamma={calculated_gamma_bs}, FinalGamma={gamma:.6f}, "
                                f"FinalVanna={vanna:.4f}, Notional={notional:.2f}"
                            )

                            final_greeks_payload = {
                                "gamma": gamma, "vanna": vanna, "charm": charm, "volga": volga,
                                "notional_usd": notional, "strike": strike,
                            }
                            greek_store[inst] = final_greeks_payload
                            
                            # gamma_by_strike should sum the FINAL gamma used
                            # This was previously outside, let's keep it simple and sum raw gamma here.
                            # The dealer netting for gamma_flip happens in maybe_publish now with current_gamma_by_strike.
                            # So this gamma_by_strike is for raw gamma exposure visualization if needed later.
                            # For flip_pct, current_gamma_by_strike (netted) is used.
                            # If you want gamma_by_strike to be always net, it must be rebuilt in maybe_publish only.
                            # For now, let's assume it's raw gamma for simplicity here, or remove its update here.
                            # Decision: Updated `gamma_by_strike` is now done in `maybe_publish` as `current_gamma_by_strike`.
                            # So, remove this line:
                            # gamma_by_strike[strike] = gamma_by_strike.get(strike, 0.0) + gamma


                            if len(greek_store) % LOG_STORE_THRESHOLD == 0 and len(greek_store) > 0:
                                logger.info(f"PROCESSOR: Stored greeks for {len(greek_store)} instruments. Latest: {inst}")
                        
                        tick_times.append(time.time())

                    except Exception as e:
                        failing_message_id = mid.decode() if isinstance(mid, bytes) else str(mid)
                        logger.error(f"PROCESSOR PARSE ERR (msg_id: {failing_message_id}): {e} -- Failing Msg: {str(raw_msg_data)[:500]}", exc_info=True)
        
        current_loop_time = time.time()
        if current_loop_time - last_pub >= ROLL_FREQ:
            await maybe_publish(redis) # Pass the global gamma_by_strike
            last_pub = current_loop_time

if __name__ == "__main__":
    try:
        asyncio.run(processor())
    except KeyboardInterrupt:
        logger.info("Processor interrupted by user.")
    except Exception as e:
        logger.critical("Processor crashed", exc_info=True)

