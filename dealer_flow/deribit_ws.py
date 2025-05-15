# dealer_flow/deribit_ws.py
import asyncio, json, time, uuid, aiohttp, websockets, orjson, sys
import logging
from dealer_flow.config import settings
from dealer_flow.redis_stream import get_redis, STREAM_KEY_RAW # Keep for raw ticker data
# New stream key for book summaries
STREAM_KEY_BOOK_SUMMARIES_FEED = "deribit_book_summaries_feed"


if __name__ == "__main__": # BasicConfig for standalone execution
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)s %(name)s:%(lineno)d - COLLECTOR: %(message)s"
        )
logger = logging.getLogger(__name__)

TOKEN_TTL = 23 * 3600

# --- Auth Token (remains largely the same, ensure logging) ---
# dealer_flow/deribit_ws.py
# ... (imports and logger setup as before) ...
STREAM_KEY_BOOK_SUMMARIES_FEED = "deribit_book_summaries_feed"
TOKEN_TTL = 23 * 3600
DERIBIT_MAX_CHANNELS_PER_REQUEST = 40 # Deribit says max 50, be a bit conservative

async def auth_token(): # No changes from your last good version
    # ...
    logger.debug(f"Attempting auth. DERIBIT_ID set: {bool(settings.deribit_id)}, DERIBIT_SECRET set: {bool(settings.deribit_secret)}")
    if not (settings.deribit_id and settings.deribit_secret):
        logger.warning("Creds absent or incomplete → unauth mode")
        return None, 0
    auth_url = f"{settings.deribit_rest}/public/auth"
    logger.debug(f"Auth URL: {auth_url}")
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                auth_url,
                params={"grant_type": "client_credentials", "client_id": settings.deribit_id, "client_secret": settings.deribit_secret},
                timeout=10,
            ) as r:
                if r.status != 200:
                    logger.error(f"Auth HTTP error - Status: {r.status}, Response: {await r.text()[:200]} → unauth mode")
                    return None, 0
                j = await r.json()
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
    logger.info("Auth OK")
    return token, time.time() + TOKEN_TTL


async def send_ws_message(ws, method, params=None):
    if not ws or ws.closed:
        logger.warning(f"WebSocket not connected or closed, cannot send {method}")
        return

    msg_id = str(uuid.uuid4())
    req = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params:
        req["params"] = params
    raw_req = orjson.dumps(req)
    logger.debug(f"> WS SEND ({method}, id:{msg_id}): {raw_req.decode()[:200]}")
    try:
        await ws.send(raw_req)
    except websockets.exceptions.ConnectionClosed:
        logger.warning(f"Attempted to send to a closed WebSocket ({method}).")
    except Exception as e:
        logger.error(f"Error sending WebSocket message ({method}): {e}", exc_info=True)


def chunk_list(data: list, size: int):
    for i in range(0, len(data), size):
        yield data[i:i + size]

async def subscribe_channels_chunked(ws, channels: list):
    if not channels:
        logger.debug("subscribe_channels_chunked called with no channels.")
        return
    for chunk in chunk_list(channels, DERIBIT_MAX_CHANNELS_PER_REQUEST):
        logger.info(f"Subscribing to chunk of {len(chunk)} channels (first: {chunk[0] if chunk else 'N/A'})...")
        await send_ws_message(ws, "public/subscribe", {"channels": chunk})
        await asyncio.sleep(0.1) # Small delay between chunked requests

async def unsubscribe_channels_chunked(ws, channels: list):
    if not channels:
        logger.debug("unsubscribe_channels_chunked called with no channels.")
        return
    for chunk in chunk_list(channels, DERIBIT_MAX_CHANNELS_PER_REQUEST):
        logger.info(f"Unsubscribing from chunk of {len(chunk)} channels (first: {chunk[0] if chunk else 'N/A'})...")
        await send_ws_message(ws, "public/unsubscribe", {"channels": chunk})
        await asyncio.sleep(0.1) # Small delay


class DeribitCollector:
    def __init__(self, redis_client):
        # ... (same as before)
        self.redis = redis_client
        self.ws = None
        self.token = None
        self.token_exp = 0
        self.is_authenticated_session = False
        self.latest_instrument_summaries = []
        self.active_ticker_subscriptions = set()
        self._new_summary_event = asyncio.Event()
        self._shutdown_event = asyncio.Event()

    async def _ensure_auth(self): # same
        # ...
        if not self.token or time.time() > self.token_exp:
            self.token, self.token_exp = await auth_token()
            self.is_authenticated_session = self.token is not None
        return self.is_authenticated_session

    async def _handle_book_summary(self, data): # same
        # ...
        if isinstance(data, list):
            self.latest_instrument_summaries = data
            self._new_summary_event.set() 
            logger.info(f"Received book_summary with {len(data)} instruments.")
            payload_to_store = { "ts": time.time(), "summary_data": data }
            try:
                await self.redis.xadd( STREAM_KEY_BOOK_SUMMARIES_FEED, {"d": orjson.dumps(payload_to_store)} )
                logger.debug(f"Pushed book_summary (len {len(data)}) to {STREAM_KEY_BOOK_SUMMARIES_FEED}")
            except Exception as e:
                logger.error(f"Redis XADD error for book_summary: {e}", exc_info=True)

        else:
            logger.warning(f"Received book_summary with unexpected data type: {type(data)}")


    async def _manage_ticker_subscriptions_task(self):
        logger.info("Dynamic ticker subscription manager task started.")
        while not self._shutdown_event.is_set():
            try:
                # Correctly await the event's wait() coroutine
                await asyncio.wait_for(self._new_summary_event.wait(), timeout=float(settings.dynamic_subscription_refresh_interval_seconds))
            except asyncio.TimeoutError:
                logger.debug("Subscription refresh interval timed out, checking summaries anyway.")
            except Exception as e: # Catch other potential errors from wait_for or wait
                logger.error(f"Error in _manage_ticker_subscriptions_task event wait: {e}", exc_info=True)
                await asyncio.sleep(5) # Avoid fast loop on unexpected error
                continue
            
            self._new_summary_event.clear()
            
            if not self.is_authenticated_session:
                logger.debug("Not authenticated, skipping dynamic subscription management.")
                await asyncio.sleep(float(settings.dynamic_subscription_refresh_interval_seconds))
                continue

            if not self.latest_instrument_summaries:
                logger.info("No instrument summaries available to manage ticker subscriptions yet.")
                await asyncio.sleep(10)
                continue

            if not self.ws or self.ws.closed:
                logger.warning("WebSocket not connected in manager task, cannot manage subscriptions.")
                await asyncio.sleep(10)
                continue

            logger.debug(f"Managing ticker subscriptions. Have {len(self.latest_instrument_summaries)} summaries.")
            
            valid_summaries = [
                s for s in self.latest_instrument_summaries 
                if isinstance(s, dict) and "instrument_name" in s and isinstance(s.get("open_interest"), (int, float))
            ]
            sorted_by_oi = sorted(valid_summaries, key=lambda x: x.get("open_interest", 0.0), reverse=True)
            
            top_n_instruments = {
                s["instrument_name"] for s in sorted_by_oi[:settings.deribit_max_auth_instruments]
            }

            logger.info(f"Targeting top {len(top_n_instruments)} instruments by OI (max_config: {settings.deribit_max_auth_instruments}).")

            to_unsubscribe_names = list(self.active_ticker_subscriptions - top_n_instruments)
            to_subscribe_names = list(top_n_instruments - self.active_ticker_subscriptions)

            if to_unsubscribe_names:
                logger.info(f"Unsubscribing from {len(to_unsubscribe_names)} tickers (chunked).")
                await unsubscribe_channels_chunked(self.ws, [f"ticker.{inst}.100ms" for inst in to_unsubscribe_names])
                self.active_ticker_subscriptions.difference_update(to_unsubscribe_names)
            
            if to_subscribe_names:
                logger.info(f"Subscribing to {len(to_subscribe_names)} new tickers (chunked).")
                await subscribe_channels_chunked(self.ws, [f"ticker.{inst}.100ms" for inst in to_subscribe_names])
                self.active_ticker_subscriptions.update(to_subscribe_names)
            
            if not to_subscribe_names and not to_unsubscribe_names:
                logger.debug("Ticker subscriptions are already up-to-date.")
            logger.info(f"Currently subscribed to {len(self.active_ticker_subscriptions)} tickers.")
        logger.info("Dynamic ticker subscription manager task stopped.")

    async def _message_handler_loop(self): # Largely same, ensure it uses new subscribe/unsubscribe
        # ...
        logger.info("Message handler loop started.")
        initial_subscriptions_done = False # Reset for new connection
        
        # Ensure self.active_ticker_subscriptions is cleared if we are re-establishing connection
        # Or better, resync it with what we *think* we should subscribe to.
        # For now, let's assume it's managed by _manage_ticker_subscriptions_task.
        # If _manage_ticker_subscriptions_task is not running (e.g. unauth), this loop won't try to manage tickers.

        while not self._shutdown_event.is_set() and self.ws and not self.ws.closed:
            if not initial_subscriptions_done:
                base_channels = [
                    f"deribit_price_index.{settings.currency.lower()}_usd",
                    f"book_summary.option.{settings.currency.lower()}.all"
                ]
                logger.info(f"Sending initial base subscriptions: {base_channels}")
                # Use chunked version, though for 2 channels it's not strictly needed
                await subscribe_channels_chunked(self.ws, base_channels)
                initial_subscriptions_done = True

            try:
                msg_raw = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                # ... (rest of message parsing logic as before)
                msg_json = orjson.loads(msg_raw)
                logger.debug(f"< WS RECV: {str(msg_raw)[:250]}") 

                method = msg_json.get("method")
                params = msg_json.get("params")

                if method == "subscription":
                    channel = params.get("channel")
                    data = params.get("data")
                    
                    if channel.startswith("book_summary.option."):
                        await self._handle_book_summary(data)
                    elif channel.startswith("deribit_price_index.") or channel.startswith("ticker."):
                        await self.redis.xadd(STREAM_KEY_RAW, {"d": msg_raw}) 
                elif msg_json.get("id") and "result" in msg_json: # Check 'id' first
                     # Check if it's a response to our public/test
                    if isinstance(msg_json["result"], dict) and msg_json["result"].get("version"):
                        logger.info(f"Received public/test response: {msg_json['result']}")
                    else:
                        logger.debug(f"Received result for request ID {msg_json['id']}: {str(msg_json['result'])[:100]}")
                elif "error" in msg_json: # This is where 11050 comes
                    logger.error(f"Received error from Deribit (request_id: {msg_json.get('id')}): {msg_json['error']}")
                
                # Test request handling - Deribit sends this, we should respond.
                elif msg_json.get("method") == "heartbeat" and msg_json.get("params", {}).get("type") == "test_request":
                    logger.info("Received test_request heartbeat from Deribit, responding.")
                    await send_ws_message(self.ws, "public/test")


            except asyncio.TimeoutError:
                if self.ws and not self.ws.closed:
                    try:
                        logger.debug("Sending keepalive (public/set_heartbeat or public/test) due to recv timeout.")
                        # Deribit recommends public/set_heartbeat to keep connection alive.
                        # If that gives errors, public/test is an alternative.
                        await send_ws_message(self.ws, "public/set_heartbeat", {"interval": 15})
                        # await send_ws_message(self.ws, "public/test") 
                    except Exception as e:
                        logger.error(f"Failed to send keepalive: {e}")
                continue 
            except websockets.exceptions.ConnectionClosed: # More specific
                logger.warning("WebSocket connection closed during recv.")
                break 
            except Exception as e:
                logger.error(f"Error in message handler loop: {e}", exc_info=True)
                await asyncio.sleep(1)
        
        logger.info("Message handler loop stopped.")

    async def run_forever(self): # Main logic same, ensure tasks are managed
        # ...
        logger.info("Collector run_forever starting.")
        subscription_manager_task_handle = None # Use a more descriptive name
        
        while not self._shutdown_event.is_set():
            await self._ensure_auth() 
            
            connect_headers = {}
            if self.token and self.is_authenticated_session:
                connect_headers["Authorization"] = f"Bearer {self.token}"
            
            mode_log = "auth" if self.is_authenticated_session else "unauth"
            logger.info(f"Attempting WebSocket connection ({mode_log} mode)...")

            try:
                # Use a new variable for the connection within the context manager
                async with websockets.connect(
                    settings.deribit_ws,
                    extra_headers=connect_headers,
                    ping_interval=20, 
                    ping_timeout=20
                ) as current_ws_connection: # New variable name
                    self.ws = current_ws_connection # Assign to the class attribute
                    logger.info(f"WebSocket connected successfully ({mode_log} mode).")

                    # Start/Restart subscription manager task if authenticated and it's not running or finished
                    if self.is_authenticated_session:
                        if subscription_manager_task_handle is None or subscription_manager_task_handle.done():
                            if subscription_manager_task_handle and subscription_manager_task_handle.done():
                                try:
                                    subscription_manager_task_handle.result() # Check for exceptions if it finished
                                except Exception as e_task:
                                    logger.error(f"Subscription manager task exited with error: {e_task}", exc_info=True)
                            logger.info("Starting/Restarting dynamic ticker subscription manager task.")
                            self._new_summary_event.clear() # Clear before starting task
                            subscription_manager_task_handle = asyncio.create_task(self._manage_ticker_subscriptions_task())
                    elif subscription_manager_task_handle and not subscription_manager_task_handle.done():
                        # If we lose auth, we might want to stop it or let it pause itself
                        logger.info("Lost authentication. Subscription manager will pause if running.")
                    
                    await self._message_handler_loop()

            except Exception as e: # Catch more specific errors first
                logger.error(f"Unhandled WebSocket connection or main loop error: {e}", exc_info=True)
            finally:
                self.ws = None 
                # Don't nullify subscription_manager_task_handle here, let it be managed by the outer loop
                # It will be restarted if needed on successful reconnect + auth.
                # If it was running and connection dropped, it should pause itself internally.
            
            if self._shutdown_event.is_set(): break
            logger.info("Sleeping for 5 seconds before attempting reconnect.")
            await asyncio.sleep(5)
        
        logger.info("Collector run_forever loop ended.")
        if subscription_manager_task_handle and not subscription_manager_task_handle.done():
            logger.info("Attempting to cancel and wait for subscription manager task...")
            subscription_manager_task_handle.cancel()
            try:
                await subscription_manager_task_handle
            except asyncio.CancelledError:
                logger.info("Subscription manager task successfully cancelled.")
            except Exception as e_task_final:
                logger.error(f"Error during final cleanup of subscription manager task: {e_task_final}")


    def stop(self): # Same
        # ...
        logger.info("Collector stop requested.")
        self._shutdown_event.set()
        if self.ws: 
            asyncio.create_task(self.ws.close(code=1000, reason="Collector shutdown"))

async def main_run_collector(): # Renamed for clarity
    # ... (same as your main_run, just using the new name)
    redis_client = await get_redis()
    collector = DeribitCollector(redis_client)
    try:
        await collector.run_forever()
    except KeyboardInterrupt:
        logger.info("Collector main_run_collector received KeyboardInterrupt.")
    finally:
        logger.info("Collector main_run_collector stopping.")
        collector.stop()

if __name__ == "__main__":
    # ... (same, calling main_run_collector)
    logger.info("Deribit WS Collector starting as main process...")
    try:
        asyncio.run(main_run_collector())
    except KeyboardInterrupt:
        logger.info("Collector stopped by KeyboardInterrupt (asyncio.run).")
    except Exception as e:
        logger.critical(f"Collector CRASHED at asyncio.run level: {e}", exc_info=True)
    finally:
        logger.info("Collector process finished.")

