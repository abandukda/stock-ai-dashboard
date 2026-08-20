-- Reference PostgreSQL schema for a future CustomerRepository adapter.
-- This file is not executed or imported by current ATLAS.

CREATE TABLE customer_users (
    user_id UUID PRIMARY KEY,
    auth_subject TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    disabled BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE customer_profiles (
    account_id UUID PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE REFERENCES customer_users(user_id),
    plan TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    beta_cohort TEXT,
    beta_enabled BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE customer_watchlists (
    watchlist_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES customer_users(user_id),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (user_id, name)
);

CREATE TABLE customer_watchlist_symbols (
    watchlist_id UUID NOT NULL REFERENCES customer_watchlists(watchlist_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES customer_users(user_id),
    security_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    security_type TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (watchlist_id, security_id),
    UNIQUE (watchlist_id, ticker)
);

CREATE TABLE customer_notification_preferences (
    user_id UUID PRIMARY KEY REFERENCES customer_users(user_id),
    enabled_channels JSONB NOT NULL,
    default_frequency TEXT NOT NULL,
    quiet_hours JSONB
);

CREATE TABLE customer_alert_preferences (
    preference_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES customer_users(user_id),
    alert_type TEXT NOT NULL,
    enabled BOOLEAN NOT NULL,
    ticker TEXT,
    threshold DOUBLE PRECISION,
    frequency TEXT NOT NULL,
    channels JSONB NOT NULL
);

CREATE TABLE customer_alert_events (
    event_id UUID PRIMARY KEY,
    ticker TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    evidence JSONB NOT NULL,
    event_fingerprint TEXT NOT NULL UNIQUE
);

CREATE TABLE customer_alert_deliveries (
    delivery_id UUID PRIMARY KEY,
    event_fingerprint TEXT NOT NULL REFERENCES customer_alert_events(event_fingerprint),
    user_id UUID NOT NULL REFERENCES customer_users(user_id),
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    UNIQUE (event_fingerprint, user_id, channel)
);

CREATE TABLE customer_saved_research (
    saved_research_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES customer_users(user_id),
    security_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    security_type TEXT NOT NULL,
    saved_at TIMESTAMPTZ NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    UNIQUE (user_id, security_id)
);

CREATE TABLE customer_feature_overrides (
    user_id UUID NOT NULL REFERENCES customer_users(user_id),
    feature_key TEXT NOT NULL,
    enabled BOOLEAN NOT NULL,
    set_by_user_id UUID NOT NULL REFERENCES customer_users(user_id),
    PRIMARY KEY (user_id, feature_key)
);
