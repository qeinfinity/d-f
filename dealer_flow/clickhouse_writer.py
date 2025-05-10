# dealer_flow/clickhouse_writer.py
import asyncio
import logging
import time
import orjson
from typing import List, Dict, Any

import aioredis
from clickhouse_driver import Client as ClickHouseClient
from clickhouse_driver.errors import ServerException as ClickHouseServerException

from dealer_flow.config import settings
from dealer_flow.redis_stream import get_redis, STREAM_KEY_METRICS # Existing metrics stream
# New stream key from collector
STREAM_KEY_BOOK_SUMMARIES_FEED = "deribit_book_summaries_feed" # Must match collector

# Configure logger for this service
if __name__ == "__main__" and not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s:%(lineno)d - CH_WRITER: %(message)s"
    )
logger = logging.getLogger(__name__)

# ClickHouse table names
TABLE_DEALER_METRICS = "dealer_flow_metrics_v1"
TABLE_INSTRUMENT_SUMMARIES = "deribit_instrument_summaries_v1"

# Consumer group and name for Redis streams
GROUP_NAME_CH_WRITER = "ch_writer_group"
CONSUMER_NAME_CH_WRITER = "ch_writer_consumer_1"

BATCH_SIZE = 100  # How many messages to accumulate before writing to ClickHouse
BATCH_MAX_AGE_SECONDS = 10 # Max age of a batch before writing, even if not full

def get_ch_client():
    logger.info(f"Connecting to ClickHouse: host={settings.clickhouse_host}, port={settings.clickhouse_port}, db={settings.clickhouse_db_name}")
    try:
        client = ClickHouseClient(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            database=settings.clickhouse_db_name,
            user=settings.clickhouse_user,
            password=settings.clickhouse_password,
            connect_timeout=10,
            send_receive_timeout=60,
            # settings={'use_numpy': True} # If sending numpy dtypes directly, but we parse to Python types
        )
        client.execute("SELECT 1") # Test connection
        logger.info("Successfully connected to ClickHouse.")
        return client
    except ClickHouseServerException as e:
        logger.error(f"ClickHouse ServerException on connect: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Failed to connect to ClickHouse: {e}", exc_info=True)
        raise

async def ensure_redis_stream_group(redis: aioredis.Redis, stream_key: str, group_name: str):
    try:
        await redis.xgroup_create(name=stream_key, groupname=group_name, id="0", mkstream=True)
        logger.info(f"Created Redis consumer group '{group_name}' for stream '{stream_key}'.")
    except aioredis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info(f"Consumer group '{group_name}' for stream '{stream_key}' already exists.")
        else:
            logger.error(f"Failed to create consumer group '{group_name}' for '{stream_key}': {e}", exc_info=True)
            raise # Re-raise if it's an unexpected error

def parse_dealer_metrics(data_str: bytes) -> Dict[str, Any]:
    # Assuming data_str is the raw JSON bytes from Redis stream 'd' field
    payload = orjson.loads(data_str)
    # Ensure all expected fields are present, with defaults for ClickHouse schema
    return {
        "ts": payload.get("ts", time.time()), # Convert to ClickHouse DateTime
        "price": payload.get("price"),
        "msg_rate": payload.get("msg_rate"),
        "NGI": payload.get("NGI"),
        "VSS": payload.get("VSS"),
        "CHL_24h": payload.get("CHL_24h"),
        "VOLG": payload.get("VOLG"),
        "flip_pct": payload.get("flip_pct"), # Already nullable in CH
        "HPP": payload.get("HPP"),
        "scenario": payload.get("scenario", "Unknown"),
    }

def parse_instrument_summary(summary_item: Dict[str, Any], received_ts: float) -> Dict[str, Any]:
    # Parse a single instrument summary from the book_summary array
    return {
        "received_ts": received_ts,
        "instrument_name": summary_item.get("instrument_name"),
        "underlying_price": summary_item.get("underlying_price"),
        "underlying_index": summary_item.get("underlying_index"),
        "quote_currency": summary_item.get("quote_currency"),
        "open_interest": summary_item.get("open_interest"),
        "volume": summary_item.get("volume"),
        "volume_usd": summary_item.get("volume_usd"),
        "bid_iv": summary_item.get("bid_iv"),
        "ask_iv": summary_item.get("ask_iv"),
        "mark_iv": summary_item.get("mark_iv"),
        "interest_rate": summary_item.get("interest_rate", 0.0), # Default if missing
        # Add other fields from book_summary if needed for table
    }


async def stream_consumer_task(
    redis: aioredis.Redis,
    ch_client: ClickHouseClient,
    stream_key: str,
    table_name: str,
    parser_func,
    shutdown_event: asyncio.Event
):
    logger.info(f"Starting consumer task for Redis stream '{stream_key}' -> ClickHouse table '{table_name}'")
    await ensure_redis_stream_group(redis, stream_key, GROUP_NAME_CH_WRITER)
    
    batch: List[Dict[str, Any]] = []
    last_batch_write_time = time.monotonic()

    while not shutdown_event.is_set():
        try:
            messages = await redis.xreadgroup(
                groupname=GROUP_NAME_CH_WRITER,
                consumername=CONSUMER_NAME_CH_WRITER,
                streams={stream_key: ">"}, # Read new messages
                count=BATCH_SIZE,
                block=1000 # Block for 1 second
            )

            if not messages:
                # No messages, check if batch should be written due to age
                if batch and (time.monotonic() - last_batch_write_time > BATCH_MAX_AGE_SECONDS):
                    logger.info(f"Writing batch to {table_name} due to age ({len(batch)} items).")
                    ch_client.execute(f"INSERT INTO {table_name} VALUES", batch)
                    # TODO: Implement XACK for processed messages
                    batch = []
                    last_batch_write_time = time.monotonic()
                continue

            message_ids_to_ack = []
            for stream_name, stream_messages in messages:
                for msg_id, msg_data_dict in stream_messages:
                    try:
                        # msg_data_dict is {'d': b'json_payload'}
                        raw_payload = msg_data_dict.get(b"d")
                        if not raw_payload:
                            logger.warning(f"Empty payload for message ID {msg_id.decode()} in stream {stream_key}")
                            message_ids_to_ack.append(msg_id) # Ack even if payload is bad to remove it
                            continue
                        
                        # Specific handling for book_summaries_feed which contains a list
                        if stream_key == STREAM_KEY_BOOK_SUMMARIES_FEED:
                            outer_payload = orjson.loads(raw_payload)
                            received_ts = outer_payload.get("ts", time.time())
                            summary_list = outer_payload.get("summary_data", [])
                            for summary_item in summary_list:
                                parsed_item = parser_func(summary_item, received_ts)
                                batch.append(parsed_item)
                        else: # For dealer_metrics (single item per message)
                            parsed_data = parser_func(raw_payload)
                            batch.append(parsed_data)
                        
                        message_ids_to_ack.append(msg_id)
                    except Exception as e:
                        logger.error(f"Failed to parse message ID {msg_id.decode()} from {stream_key}: {e}", exc_info=True)
                        # Optionally, could move bad messages to a dead-letter queue instead of just acking
                        message_ids_to_ack.append(msg_id) # Ack to prevent reprocessing bad message

            if batch and (len(batch) >= BATCH_SIZE or (time.monotonic() - last_batch_write_time > BATCH_MAX_AGE_SECONDS)):
                logger.info(f"Writing batch to {table_name} (size: {len(batch)}).")
                try:
                    ch_client.execute(f"INSERT INTO {table_name} VALUES", batch)
                    if message_ids_to_ack: # Ack messages after successful insert
                        await redis.xack(stream_key, GROUP_NAME_CH_WRITER, *message_ids_to_ack)
                    batch = []
                    last_batch_write_time = time.monotonic()
                except ClickHouseServerException as e:
                    logger.error(f"ClickHouseServerException during batch insert to {table_name}: {e}", exc_info=True)
                    # Batch will be retried in the next loop iteration if not cleared
                    # Consider more sophisticated retry/dead-letter queue for persistent CH errors
                    await asyncio.sleep(5) # Wait before retrying CH
                except Exception as e:
                    logger.error(f"Generic error during batch insert to {table_name}: {e}", exc_info=True)
                    await asyncio.sleep(5)


        except aioredis.exceptions.BusyLoadingError:
            logger.warning("Redis busy loading, ClickHouse writer pausing...")
            await asyncio.sleep(5)
        except (aioredis.exceptions.ConnectionError, ConnectionRefusedError) as e:
            logger.error(f"Redis connection error in ClickHouse writer: {e}. Retrying connection...", exc_info=True)
            await asyncio.sleep(5)
            try: # Try to re-establish redis connection
                redis = await get_redis()
                await ensure_redis_stream_group(redis, stream_key, GROUP_NAME_CH_WRITER)
                logger.info("Re-established Redis connection for ClickHouse writer.")
            except Exception as recon_e:
                logger.error(f"Failed to re-establish Redis connection: {recon_e}", exc_info=True)
                await asyncio.sleep(10) # Longer sleep if reconnect fails
        except Exception as e:
            logger.error(f"Unhandled error in ClickHouse writer for stream {stream_key}: {e}", exc_info=True)
            await asyncio.sleep(10) # Sleep on unhandled error to prevent rapid crash loops
    
    # Final batch write on shutdown
    if batch:
        logger.info(f"Shutdown: Writing final batch to {table_name} (size: {len(batch)}).")
        try:
            ch_client.execute(f"INSERT INTO {table_name} VALUES", batch)
            # Ack for final batch if needed, though consumer might be gone
        except Exception as e:
            logger.error(f"Error writing final batch to {table_name} on shutdown: {e}", exc_info=True)
    logger.info(f"Consumer task for stream '{stream_key}' stopped.")


async def main():
    logger.info("ClickHouse Writer Service starting...")
    redis_client = await get_redis()
    # TODO: Implement wait_for_redis(redis_client) here
    if not await wait_for_redis(redis_client): # Assuming wait_for_redis is defined as in processor
        logger.critical("ClickHouse Writer cannot start: Redis not available.")
        return

    try:
        ch_client = get_ch_client()
    except Exception:
        logger.critical("Failed to connect to ClickHouse on startup. Exiting.")
        return

    shutdown_event = asyncio.Event()
    
    # Create tasks for each stream
    metrics_task = asyncio.create_task(
        stream_consumer_task(redis_client, ch_client, STREAM_KEY_METRICS, TABLE_DEALER_METRICS, parse_dealer_metrics, shutdown_event)
    )
    summaries_task = asyncio.create_task(
        stream_consumer_task(redis_client, ch_client, STREAM_KEY_BOOK_SUMMARIES_FEED, TABLE_INSTRUMENT_SUMMARIES, parse_instrument_summary, shutdown_event)
    )

    try:
        await asyncio.gather(metrics_task, summaries_task)
    except KeyboardInterrupt:
        logger.info("ClickHouse Writer received KeyboardInterrupt.")
    finally:
        logger.info("ClickHouse Writer shutting down tasks...")
        shutdown_event.set()
        # Wait for tasks to complete with a timeout
        try:
            await asyncio.wait_for(asyncio.gather(metrics_task, summaries_task, return_exceptions=True), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for consumer tasks to finish.")
        if ch_client:
            ch_client.disconnect()
        logger.info("ClickHouse Writer service stopped.")

if __name__ == "__main__":
    asyncio.run(main())
