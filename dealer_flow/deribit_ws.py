# dealer_flow/deribit_ws.py
import asyncio, json, time, uuid, aiohttp, websockets, orjson, sys
import logging
from dealer_flow.config import settings # Make sure settings is imported
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW

# This basicConfig should apply since this script is run as __main__ for the collector process
if __name__ == "__main__" and not logging.getLogger().hasHandlers(): # Ensure basicConfig is only called once
    logging.basicConfig(
        level=logging.DEBUG, # <--- SET TO DEBUG for more verbosity
        format="%(asctime)s %(levelname)s %(name)s:%(lineno)d - COLLECTOR: %(message)s" # Add COLLECTOR prefix
    )
logger = logging.getLogger(__name__)

TOKEN_TTL = 23 * 3600
MAX_UNAUTH_STRIKES = 12 # For unauthenticated mode

# This should be in config.py and .env / .env.example
# For now, if not in settings, we'll use a default here to ensure code runs.
# Ideally: DERIBIT_MAX_AUTH_INSTRUMENTS = 100 in config.py (loaded from .env)
DEFAULT_MAX_AUTH_INSTRUMENTS = 100


async def auth_token():
    # Add some debug logging for settings
    logger.debug(f"Attempting auth. DERIBIT_ID set: {bool(settings.deribit_id)}, DERIBIT_SECRET set: {bool(settings.deribit_secret)}")
    if not (settings.deribit_id and settings.deribit_secret):
        logger.warning("Creds absent or incomplete (ID or Secret missing) → unauth mode")
        return None, 0
    
    # Ensure URL is correct
    auth_url = f"{settings.deribit_rest}/public/auth"
    logger.debug(f"Auth URL: {auth_url}")

    async with aiohttp.ClientSession() as sess:
        try:
            r = await sess.get(
                auth_url,
                params={
                    "grant_type": "client_credentials",
                    "client_id": settings.deribit_id,
                    "client_secret": settings.deribit_secret,
                },
                timeout=10,
            )
            # Check HTTP status for auth call itself
            if r.status != 200:
                logger.error(f"Auth HTTP error - Status: {r.status}, Response: {await r.text()[:200]} → unauth mode")
                return None, 0
            j = await r.json()
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Auth HTTP connection error: {e} → unauth mode", exc_info=True)
            return None, 0
        except Exception as e:
            logger.error(f"Auth generic error: {e} → unauth mode", exc_info=True)
            return None, 0

    if "error" in j:
        logger.error(f"Auth rejected by API: {j.get('error_description', j['error'])} → unauth mode")
        return None, 0
    
    token = j.get("result", {}).get("access_token")
    if not token:
        logger.error(f"Auth response OK but no access_token in result {j} → unauth mode")
        return None, 0

    logger.info("Auth OK") # This is appearing in your logs
    return token, time.time() + TOKEN_TTL

# dealer_flow/deribit_ws.py

# ... (imports and other functions remain the same) ...
# Ensure logger is set up as in the previous patch (DEBUG level)

async def current_instruments(is_authenticated: bool):
    logger.info(f"Entering current_instruments. is_authenticated: {is_authenticated}")
    # print(f"DEBUG_PRINT: Entering current_instruments. is_authenticated: {is_authenticated}", file=sys.stderr); sys.stderr.flush()

    instruments_url = f"{settings.deribit_rest}/public/get_instruments"
    params=dict(currency=settings.currency, kind="option", expired="false")
    logger.debug(f"Fetching instruments from URL: {instruments_url} with params: {params}")
    # print(f"DEBUG_PRINT: Fetching instruments from URL: {instruments_url} with params: {params}", file=sys.stderr); sys.stderr.flush()

    api_data_result = [] # Initialize to ensure it's a list
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(instruments_url, params=params, timeout=20) as r:
                logger.debug(f"get_instruments HTTP status: {r.status}")
                # print(f"DEBUG_PRINT: get_instruments HTTP status: {r.status}", file=sys.stderr); sys.stderr.flush()
                response_text_snippet = await r.text()
                response_text_snippet = response_text_snippet[:500]

                if r.status != 200:
                    logger.error(f"HTTP error fetching instruments: {r.status}. Response: {response_text_snippet}")
                    return [] 
                try:
                    json_response = await r.json(content_type=None)
                    logger.debug(f"get_instruments JSON response (first 200 chars): {str(json_response)[:200]}")
                    api_data_result = json_response.get("result", []) # Assign to api_data_result
                    if not isinstance(api_data_result, list):
                        logger.error(f"API 'result' for get_instruments is not a list. Type: {type(api_data_result)}. Payload: {str(json_response)[:500]}")
                        api_data_result = []
                except json.JSONDecodeError as json_err:
                    logger.error(f"JSON decode error fetching instruments: {json_err}. Response text: {response_text_snippet}", exc_info=True)
                    return []
    except Exception as e:
        logger.error(f"Generic error during instrument fetch API call: {e}", exc_info=True)
        return []

    logger.info(f"Raw instrument data fetched from API, count: {len(api_data_result)}. First item if any: {str(api_data_result[0])[:200] if api_data_result else 'N/A'}")
    # print(f"DEBUG_PRINT: Raw data fetched, count: {len(api_data_result)}. First item if any: {str(api_data_result[0])[:200] if api_data_result else 'N/A'}", file=sys.stderr); sys.stderr.flush()

    selected_instrument_names = []

    if not api_data_result: # Check if api_data_result is empty
        logger.warning("No instrument data received from API's 'result' field or API call failed.")
        return []

    # Filter for items that are dicts and have 'instrument_name'
    # The /public/get_instruments endpoint DOES NOT contain 'open_interest'
    # So we cannot filter or sort by it here.
    
    valid_items_with_name = []
    for idx, d_item in enumerate(api_data_result): # Iterate over api_data_result
        if not isinstance(d_item, dict):
            logger.warning(f"Item {idx} in instrument data is not a dict: {str(d_item)[:100]}")
            continue
        if "instrument_name" in d_item:
            valid_items_with_name.append(d_item)
        else:
            logger.debug(f"Filtering out instrument because it's missing 'instrument_name': {str(d_item)[:100]}")

    logger.info(f"Found {len(valid_items_with_name)} instruments with an 'instrument_name' field from the API response.")
    # print(f"DEBUG_PRINT: Found {len(valid_items_with_name)} instruments with an 'instrument_name' field.", file=sys.stderr); sys.stderr.flush()
            
    if not valid_items_with_name:
        logger.warning("No instruments with 'instrument_name' found after basic validation. Returning empty list.")
        # print("DEBUG_PRINT: No instruments with 'instrument_name' found. Returning empty list.", file=sys.stderr); sys.stderr.flush()
        return []

    if not is_authenticated:
        logger.info(f"UNAUTH mode: Selecting up to {MAX_UNAUTH_STRIKES} instruments from {len(valid_items_with_name)} valid fetched items (Deribit default sort).")
        # print(f"DEBUG_PRINT: UNAUTH mode: Selecting up to {MAX_UNAUTH_STRIKES} from {len(valid_items_with_name)}.", file=sys.stderr); sys.stderr.flush()
        selected_instrument_names = [d["instrument_name"] for d in valid_items_with_name[:MAX_UNAUTH_STRIKES]]
    else: # Authenticated mode
        max_instruments_to_subscribe = settings.deribit_max_auth_instruments
        logger.info(f"AUTH mode: Selecting up to {max_instruments_to_subscribe} instruments from {len(valid_items_with_name)} valid fetched items (Deribit default sort).")
        # print(f"DEBUG_PRINT: AUTH mode: Selecting up to {max_instruments_to_subscribe} from {len(valid_items_with_name)}.", file=sys.stderr); sys.stderr.flush()
        selected_instrument_names = [d["instrument_name"] for d in valid_items_with_name[:max_instruments_to_subscribe]]

    logger.info(f"Exiting current_instruments, selected {len(selected_instrument_names)} instruments for subscription.")
    # print(f"DEBUG_PRINT: Exiting current_instruments, returning {len(selected_instrument_names)} instruments.", file=sys.stderr); sys.stderr.flush()
    return selected_instrument_names

# ... (rest of deribit_ws.py, including the run function, remains the same as the previous good version) ...
# Make sure the logger setup at the top of the file is also present.


async def run():
    # ... (ensure redis connection and wait_for_redis as before)
    redis = await get_redis() # Simplified for example
    # await wait_for_redis(redis) # Assume this is handled if needed by processor's pattern

    logger.info("Collector process starting run loop.") # Changed from "COLLECTOR: launching …"
    print("DEBUG_PRINT: Collector process starting run loop.", file=sys.stderr)
    sys.stderr.flush()


    while True:
        token, token_exp = await auth_token()
        is_authenticated_session = token is not None
        logger.debug(f"Run loop: Auth status: {is_authenticated_session}, Token: {'SET' if token else 'NOT_SET'}")
        print(f"DEBUG_PRINT: Run loop: Auth status: {is_authenticated_session}, Token: {'SET' if token else 'NOT_SET'}", file=sys.stderr)
        sys.stderr.flush()


        instruments_to_watch = [] # Ensure it's defined
        try:
            instruments_to_watch = await current_instruments(is_authenticated_session)
        except Exception as e:
            logger.error(f"Critical unhandled error calling current_instruments: {e}", exc_info=True)
            print(f"DEBUG_PRINT: Critical unhandled error calling current_instruments: {e}", file=sys.stderr)
            sys.stderr.flush()
            instruments_to_watch = [] # Ensure it's an empty list on such failure
            await asyncio.sleep(15) # Wait before retrying loop
            continue
        
        logger.info(f"current_instruments returned {len(instruments_to_watch)} instruments.")
        print(f"DEBUG_PRINT: current_instruments returned {len(instruments_to_watch)} instruments.", file=sys.stderr)
        sys.stderr.flush()

        if not instruments_to_watch:
            logger.warning("No instruments selected to watch by current_instruments. Retrying instrument fetch in 30s.")
            print("DEBUG_PRINT: No instruments selected to watch by current_instruments. Retrying instrument fetch in 30s.", file=sys.stderr)
            sys.stderr.flush()
            await asyncio.sleep(30)
            continue # Go to next iteration of while True to re-fetch instruments

        # ... (rest of your subscription and streaming logic)
        spot_ch = f"deribit_price_index.{settings.currency.lower()}_usd"
        subs = [spot_ch]
        subs.extend([f"ticker.{i}.100ms" for i in instruments_to_watch])
        
        mode = "auth" if is_authenticated_session else "unauth"
        logger.info(f"Connecting ({mode}), {len(subs)} channels (spot + {len(instruments_to_watch)} option tickers)...")
        print(f"DEBUG_PRINT: Connecting ({mode}), {len(subs)} channels (spot + {len(instruments_to_watch)} option tickers)...", file=sys.stderr)
        sys.stderr.flush()


        try:
            async with websockets.connect(
                settings.deribit_ws, extra_headers=({"Authorization": f"Bearer {token}"} if token else {}), ping_interval=20
            ) as ws:
                # ... subscribe logic ...
                req = {
                    "jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "public/subscribe",
                    "params": {"channels": subs},
                }
                await ws.send(orjson.dumps(req).decode())
                logger.info("Subscribed to channels, streaming data...")
                print("DEBUG_PRINT: Subscribed to channels, streaming data...", file=sys.stderr)
                sys.stderr.flush()
                
                cnt = 0
                async for msg in ws:
                    await redis.xadd(STREAM_KEY_RAW, {"d": msg.encode()}) # Ensure redis is defined and connected
                    cnt += 1
                    if cnt % 500 == 0: # Adjust threshold as needed
                        logger.info(f"Pushed {cnt} msgs to Redis stream '{STREAM_KEY_RAW}'.")
                        print(f"DEBUG_PRINT: Pushed {cnt} msgs to Redis stream '{STREAM_KEY_RAW}'.", file=sys.stderr)
                        sys.stderr.flush()

        except websockets.exceptions.ConnectionClosedError as cce:
            logger.error(f"WebSocket ConnectionClosedError: {cce} – reconnect in 5s", exc_info=True)
        except Exception as e: # Catch other websocket errors
            logger.error(f"WebSocket error: {e} – reconnect in 5s", exc_info=True)
        
        print("DEBUG_PRINT: Websocket connection lost or error, sleeping before reconnect.", file=sys.stderr)
        sys.stderr.flush()
        await asyncio.sleep(5)


if __name__ == "__main__":
    # Initial log to confirm entry
    print("DEBUG_PRINT: deribit_ws.py __main__ starting.", file=sys.stderr)
    sys.stderr.flush()
    
    # Ensure redis client is initialized for the main run, if run standalone for testing.
    # loop = asyncio.get_event_loop()
    # redis_client_main = loop.run_until_complete(get_redis()) # Example, adapt if needed
    # if not loop.run_until_complete(wait_for_redis(redis_client_main)):
    #     print("CRITICAL: Redis not available for standalone deribit_ws.py. Exiting.", file=sys.stderr)
    #     sys.exit(1)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Collector interrupted by user, exiting.")
        print("DEBUG_PRINT: Collector interrupted by user, exiting.", file=sys.stderr)
        sys.stderr.flush()
    except Exception as e:
        logger.critical(f"Collector asyncio.run() CRASHED: {e}", exc_info=True)
        print(f"DEBUG_PRINT: Collector asyncio.run() CRASHED: {e}", file=sys.stderr)
        sys.stderr.flush()

