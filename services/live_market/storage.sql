-- Phase 8A durable PostgreSQL contract. This migration is not executed here.
-- The gateway role should receive INSERT/SELECT and narrowly scoped UPSERT
-- rights, never schema-owner credentials.

CREATE TABLE IF NOT EXISTS live_market_state (
    ticker text PRIMARY KEY,
    security_type text NOT NULL CHECK (security_type IN ('STOCK','ETF','UNKNOWN')),
    live_price numeric,
    market_timestamp timestamptz,
    received_timestamp timestamptz,
    market_session text NOT NULL,
    feed text NOT NULL,
    freshness_age_seconds double precision NOT NULL,
    stale boolean NOT NULL,
    feed_health text NOT NULL,
    last_sequence bigint,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS market_minute_bars (
    ticker text NOT NULL,
    market_timestamp timestamptz NOT NULL,
    feed text NOT NULL,
    open numeric NOT NULL,
    high numeric NOT NULL,
    low numeric NOT NULL,
    close numeric NOT NULL,
    volume numeric NOT NULL,
    trade_count bigint,
    vwap numeric,
    received_timestamp timestamptz NOT NULL,
    event_fingerprint text NOT NULL UNIQUE,
    PRIMARY KEY (ticker, market_timestamp, feed)
);

CREATE TABLE IF NOT EXISTS user_watchlists (
    watchlist_id uuid PRIMARY KEY,
    user_id text NOT NULL,
    name text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS watchlist_symbols (
    watchlist_id uuid NOT NULL REFERENCES user_watchlists(watchlist_id) ON DELETE CASCADE,
    ticker text NOT NULL,
    security_type text NOT NULL CHECK (security_type IN ('STOCK','ETF','UNKNOWN')),
    alert_enabled boolean NOT NULL DEFAULT true,
    minimum_urgency text NOT NULL DEFAULT 'NORMAL',
    alert_preferences jsonb NOT NULL DEFAULT '{}'::jsonb,
    added_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (watchlist_id, ticker)
);

CREATE TABLE IF NOT EXISTS monitoring_symbol_demand (
    source_id text NOT NULL,
    ticker text NOT NULL,
    monitoring_tier smallint NOT NULL CHECK (monitoring_tier BETWEEN 1 AND 4),
    active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, ticker)
);

CREATE TABLE IF NOT EXISTS technical_symbol_state (
    ticker text PRIMARY KEY,
    state text NOT NULL CHECK (state IN ('NO_SETUP','SETUP_FORMING','NEAR_BREAKOUT','BREAKOUT_CONFIRMED','EXTENDED','FAILED_BREAKOUT')),
    state_timestamp timestamptz NOT NULL,
    evidence jsonb NOT NULL,
    feed_health text NOT NULL,
    algorithm_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alert_events (
    event_id uuid PRIMARY KEY,
    ticker text NOT NULL,
    previous_state text NOT NULL,
    new_state text NOT NULL,
    event_timestamp timestamptz NOT NULL,
    evidence jsonb NOT NULL,
    urgency text NOT NULL,
    event_fingerprint text NOT NULL UNIQUE,
    feed_health text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alert_event_recipients (
    event_id uuid NOT NULL REFERENCES alert_events(event_id) ON DELETE CASCADE,
    user_id text NOT NULL,
    delivery_status text NOT NULL DEFAULT 'PENDING',
    delivered_at timestamptz,
    PRIMARY KEY (event_id, user_id)
);
