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
async def auth_token():
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

# --- WebSocket Message Sending Utilities ---
async def send_ws_message(ws, method, params=None):
    msg_id = str(uuid.uuid4())
    req = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params:
        req["params"] = params
    raw_req = orjson.dumps(req)
    logger.debug(f"> WS SEND ({method}, id:{msg_id}): {raw_req.decode()[:200]}") # Log message type
    await ws.send(raw_req)
    # TODO: Optionally, could implement logic to wait for and match response by ID for critical messages

async def subscribe_channels(ws, channels):
    if not channels:
        logger.warning("Subscribe called with no channels.")
        return
    await send_ws_message(ws, "public/subscribe", {"channels": channels})

async def unsubscribe_channels(ws, channels):
    if not channels:
        logger.warning("Unsubscribe called with no channels.")
        return
    await send_ws_message(ws, "public/unsubscribe", {"channels": channels})


class DeribitCollector:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.ws = None
        self.token = None
        self.token_exp = 0
        self.is_authenticated_session = False
        
        self.latest_instrument_summaries = [] # Stores the list of dicts from book_summary
        self.active_ticker_subscriptions = set() # Stores names like "BTC-26JUL24-80000-C"
        
        self._new_summary_event = asyncio.Event()
        self._shutdown_event = asyncio.Event()

    async def _ensure_auth(self):
        if not self.token or time.time() > self.token_exp:
            self.token, self.token_exp = await auth_token()
            self.is_authenticated_session = self.token is not None
        return self.is_authenticated_session

    async def _handle_book_summary(self, data):
        if isinstance(data, list):
            self.latest_instrument_summaries = data
            self._new_summary_event.set() # Signal that new summaries are available
            logger.info(f"Received book_summary with {len(data)} instruments.")
            
            # Push to Redis stream for ClickHouse writer
            payload_to_store = {
                "ts": time.time(), # Timestamp when collector received it
                "summary_data": data # Store the whole list as received
            }
            await self.redis.xadd(
                STREAM_KEY_BOOK_SUMMARIES_FEED,
                {"d": orjson.dumps(payload_to_store)}
            )
            logger.debug(f"Pushed book_summary (len {len(data)}) to {STREAM_KEY_BOOK_SUMMARIES_FEED}")
        else:
            logger.warning(f"Received book_summary with unexpected data type: {type(data)}")

    async def _manage_ticker_subscriptions_task(self):
        logger.info("Dynamic ticker subscription manager task started.")
        while not self._shutdown_event.is_set():
            try:
                await asyncio.wait_for(self._new_summary_event.wait(), timeout=settings.dynamic_subscription_refresh_interval_seconds)
            except asyncio.TimeoutError:
                logger.debug("Subscription refresh interval timed out, checking summaries anyway.")
            
            self._new_summary_event.clear() # Reset event
            
            if not self.is_authenticated_session: # Only manage dynamically if authenticated
                logger.debug("Not authenticated, skipping dynamic subscription management.")
                await asyncio.sleep(settings.dynamic_subscription_refresh_interval_seconds) # Check again later
                continue

            if not self.latest_instrument_summaries:
                logger.warning("No instrument summaries available to manage ticker subscriptions.")
                await asyncio.sleep(10) # Wait a bit before retrying
                continue

            if not self.ws or self.ws.closed:
                logger.warning("WebSocket not connected, cannot manage subscriptions.")
                await asyncio.sleep(10)
                continue

            logger.debug(f"Managing ticker subscriptions. Found {len(self.latest_instrument_summaries)} total summaries.")
            
            # Filter for valid summaries and sort by Open Interest
            valid_summaries = [
                s for s in self.latest_instrument_summaries 
                if isinstance(s, dict) and "instrument_name" in s and isinstance(s.get("open_interest"), (int, float))
            ]
            
            sorted_by_oi = sorted(valid_summaries, key=lambda x: x.get("open_interest", 0.0), reverse=True)
            
            top_n_instruments = {
                s["instrument_name"] for s in sorted_by_oi[:settings.deribit_max_auth_instruments]
            }

            logger.info(f"Targeting top {len(top_n_instruments)} instruments by OI (max_config: {settings.deribit_max_auth_instruments}).")

            to_subscribe = list(top_n_instruments - self.active_ticker_subscriptions)
            to_unsubscribe = list(self.active_ticker_subscriptions - top_n_instruments)

            if to_unsubscribe:
                logger.info(f"Unsubscribing from {len(to_unsubscribe)} tickers: {to_unsubscribe[:5]}...") # Log first 5
                await unsubscribe_channels(self.ws, [f"ticker.{inst}.100ms" for inst in to_unsubscribe])
                self.active_ticker_subscriptions.difference_update(to_unsubscribe)
            
            if to_subscribe:
                logger.info(f"Subscribing to {len(to_subscribe)} new tickers: {to_subscribe[:5]}...") # Log first 5
                await subscribe_channels(self.ws, [f"ticker.{inst}.100ms" for inst in to_subscribe])
                self.active_ticker_subscriptions.update(to_subscribe)
            
            if not to_subscribe and not to_unsubscribe:
                logger.debug("Ticker subscriptions are already up-to-date with top N by OI.")

            logger.info(f"Currently subscribed to {len(self.active_ticker_subscriptions)} tickers.")

        logger.info("Dynamic ticker subscription manager task stopped.")

    async def _message_handler_loop(self):
        logger.info("Message handler loop started.")
        initial_subscriptions_done = False
        while not self._shutdown_event.is_set() and self.ws and not self.ws.closed:
            if not initial_subscriptions_done:
                # Base subscriptions
                base_channels = [
                    f"deribit_price_index.{settings.currency.lower()}_usd",
                    f"book_summary.option.{settings.currency.lower()}.all"
                ]
                logger.info(f"Sending initial base subscriptions: {base_channels}")
                await subscribe_channels(self.ws, base_channels)
                initial_subscriptions_done = True # Set after sending

            try:
                msg_raw = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                msg_json = orjson.loads(msg_raw)
                logger.debug(f"< WS RECV: {str(msg_raw)[:250]}") # Log raw for debug

                method = msg_json.get("method")
                params = msg_json.get("params")

                if method == "subscription":
                    channel = params.get("channel")
                    data = params.get("data")
                    
                    if channel.startswith("book_summary.option."):
                        await self._handle_book_summary(data)
                    elif channel.startswith("deribit_price_index.") or channel.startswith("ticker."):
                        # Push all ticker and index data to dealer_raw for processor
                        await self.redis.xadd(STREAM_KEY_RAW, {"d": msg_raw}) # Store raw original message
                    # else: # Other subscriptions we might add in future
                        # logger.debug(f"Data on unhandled channel: {channel}")
                elif "id" in msg_json and "result" in msg_json:
                    logger.debug(f"Received result for request ID {msg_json['id']}: {str(msg_json['result'])[:100]}")
                elif "error" in msg_json:
                    logger.error(f"Received error from Deribit: {msg_json['error']}")
                # Handle heartbeat/test requests if Deribit sends them via JSON-RPC
                elif msg_json.get("method") == "public/test":
                    await send_ws_message(self.ws, "public/test")


            except asyncio.TimeoutError:
                # No message received, good time to send a keepalive if needed or check connection
                if self.ws and not self.ws.closed:
                    try:
                        logger.debug("Sending heartbeat (public/test) due to recv timeout.")
                        await send_ws_message(self.ws, "public/test")
                    except Exception as e:
                        logger.error(f"Failed to send heartbeat: {e}")
                        # This might indicate connection is truly dead, loop will break on next ws.recv()
                continue # Continue to next iteration of recv
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed during recv.")
                break # Exit message handler loop
            except Exception as e:
                logger.error(f"Error in message handler loop: {e}", exc_info=True)
                # Potentially break or sleep depending on error severity
                await asyncio.sleep(1) # Brief pause after an error
        
        logger.info("Message handler loop stopped.")


    async def run_forever(self):
        logger.info("Collector run_forever starting.")
        subscription_manager_task = None
        
        while not self._shutdown_event.is_set():
            await self._ensure_auth() # Ensure we have a token if possible
            
            connect_headers = {}
            if self.token and self.is_authenticated_session:
                connect_headers["Authorization"] = f"Bearer {self.token}"
            
            mode_log = "auth" if self.is_authenticated_session else "unauth"
            logger.info(f"Attempting WebSocket connection ({mode_log} mode)...")

            try:
                async with websockets.connect(
                    settings.deribit_ws,
                    extra_headers=connect_headers,
                    ping_interval=20, # websockets library handles pings
                    ping_timeout=20
                ) as ws_connection:
                    self.ws = ws_connection
                    logger.info(f"WebSocket connected successfully ({mode_log} mode).")

                    if self.is_authenticated_session and subscription_manager_task is None:
                         # Start manager task only if authenticated and not already running
                        subscription_manager_task = asyncio.create_task(self._manage_ticker_subscriptions_task())
                    
                    # Run message handler
                    await self._message_handler_loop()

            except websockets.exceptions.InvalidStatusCode as e:
                logger.error(f"WebSocket connection failed with status: {e.status_code} {e.headers}. Retrying in 10s.")
            except websockets.exceptions.ConnectionClosedError as e:
                logger.warning(f"WebSocket connection closed: {e}. Retrying in 5s.")
            except ConnectionRefusedError:
                logger.error("WebSocket connection refused. Retrying in 10s.")
            except Exception as e:
                logger.error(f"Unhandled WebSocket connection error: {e}", exc_info=True)
            finally:
                self.ws = None # Clear ws on disconnect
                if subscription_manager_task and not self.is_authenticated_session:
                    # If we lost auth and task was running, it should stop or be cancelled
                    logger.info("Lost authentication, ensuring subscription manager stops if running.")
                    # The task itself checks self.is_authenticated_session, so it should pause.
                    # For a hard stop, you might need cancellation logic.

            if self._shutdown_event.is_set(): break
            logger.info("Sleeping for 5 seconds before attempting reconnect.")
            await asyncio.sleep(5)
        
        logger.info("Collector run_forever loop ended.")
        if subscription_manager_task:
            logger.info("Waiting for subscription manager task to finish...")
            await subscription_manager_task # Allow it to finish gracefully

    def stop(self):
        logger.info("Collector stop requested.")
        self._shutdown_event.set()
        if self.ws: # Attempt graceful close if connected
            asyncio.create_task(self.ws.close(code=1000, reason="Collector shutdown"))


async def main_run(): # Renamed from 'run' to avoid conflict if this file is imported
    redis_client = await get_redis()
    # TODO: Add wait_for_redis(redis_client) here if needed, like in processor
    
    collector = DeribitCollector(redis_client)
    try:
        await collector.run_forever()
    except KeyboardInterrupt:
        logger.info("Collector main_run received KeyboardInterrupt.")
    finally:
        logger.info("Collector main_run stopping.")
        collector.stop()
        # Potentially wait for tasks to fully complete if needed
        # await asyncio.sleep(1) # Short delay for cleanup

if __name__ == "__main__":
    logger.info("Deribit WS Collector starting as main process...")
    try:
        asyncio.run(main_run())
    except KeyboardInterrupt:
        logger.info("Collector stopped by KeyboardInterrupt (asyncio.run).")
    except Exception as e:
        logger.critical(f"Collector CRASHED at asyncio.run level: {e}", exc_info=True)
    finally:
        logger.info("Collector process finished.")

