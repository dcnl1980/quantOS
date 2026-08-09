CREATE DATABASE IF NOT EXISTS quant;

CREATE TABLE IF NOT EXISTS quant.ticks (
    ts DateTime64(3, 'UTC'),
    venue String,
    symbol String,
    bid Float64,
    ask Float64,
    bid_size Float64,
    ask_size Float64,
    sequence Nullable(Int64),
    payload String
) ENGINE = MergeTree
ORDER BY (symbol, venue, ts);

CREATE TABLE IF NOT EXISTS quant.book_updates (
    ts DateTime64(3, 'UTC'),
    venue String,
    symbol String,
    first_update_id Int64,
    final_update_id Int64,
    is_snapshot UInt8,
    payload String
) ENGINE = MergeTree
ORDER BY (symbol, venue, ts);
