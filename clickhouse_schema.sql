-- File: ./clickhouse_schema.sql

CREATE TABLE IF NOT EXISTS dealer_flow.dealer_flow_metrics_v1
(
    ts DateTime64(3, 'UTC') CODEC(Delta, ZSTD(1)),
    price Float64 CODEC(Gorilla, ZSTD(1)),
    msg_rate Int32 CODEC(T64, ZSTD(1)),
    NGI Float64 CODEC(Gorilla, ZSTD(1)),
    VSS Float64 CODEC(Gorilla, ZSTD(1)),
    CHL_24h Float64 CODEC(Gorilla, ZSTD(1)),
    VOLG Float64 CODEC(Gorilla, ZSTD(1)),
    flip_pct Nullable(Float64) CODEC(Gorilla, ZSTD(1)),
    HPP Float64 CODEC(Gorilla, ZSTD(1)),
    scenario LowCardinality(String) CODEC(ZSTD(1))
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(ts)
ORDER BY (ts)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS dealer_flow.deribit_instrument_summaries_v1
(
    received_ts DateTime64(3, 'UTC') CODEC(Delta, ZSTD(1)),
    instrument_name LowCardinality(String) CODEC(ZSTD(1)),
    underlying_price Float64 CODEC(Gorilla, ZSTD(1)),
    underlying_index LowCardinality(String) CODEC(ZSTD(1)),
    quote_currency LowCardinality(String) CODEC(ZSTD(1)),
    open_interest Float64 CODEC(Gorilla, ZSTD(1)),
    volume Float64 CODEC(Gorilla, ZSTD(1)),
    volume_usd Float64 CODEC(Gorilla, ZSTD(1)),
    bid_iv Nullable(Float64) CODEC(Gorilla, ZSTD(1)),
    ask_iv Nullable(Float64) CODEC(Gorilla, ZSTD(1)),
    mark_iv Nullable(Float64) CODEC(Gorilla, ZSTD(1)),
    interest_rate Float64 CODEC(Gorilla, ZSTD(1))
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(received_ts)
ORDER BY (instrument_name, received_ts)
SETTINGS index_granularity = 8192;
