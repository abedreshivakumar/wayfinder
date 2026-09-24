"""The database schema. Every statement is IF NOT EXISTS, so opening a database is
always safe. Changing a table means adding a migration here, in one place."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    kind       INTEGER NOT NULL,
    file       TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    start_col  INTEGER NOT NULL,
    end_line   INTEGER NOT NULL,
    end_col    INTEGER NOT NULL,
    language   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    from_id   TEXT NOT NULL REFERENCES nodes(id),
    to_id     TEXT NOT NULL REFERENCES nodes(id),
    direction TEXT NOT NULL,
    PRIMARY KEY (from_id, to_id)
);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id);

CREATE TABLE IF NOT EXISTS call_labels (
    caller_id    TEXT NOT NULL REFERENCES nodes(id),
    callee_id    TEXT NOT NULL REFERENCES nodes(id),
    line         INTEGER NOT NULL,
    args_json    TEXT NOT NULL,
    returns_var  TEXT,
    returns_type TEXT,
    PRIMARY KEY (caller_id, callee_id, line)
);

CREATE TABLE IF NOT EXISTS flow_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_id   TEXT NOT NULL REFERENCES nodes(id),
    caller      TEXT NOT NULL,
    var         TEXT NOT NULL,
    type        TEXT,
    producer    TEXT NOT NULL,
    consumer    TEXT NOT NULL,
    producer_id TEXT,
    consumer_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_flow_links_caller ON flow_links(caller_id);

-- Generated explanations. Kept apart from `nodes` so re-saving a graph (which upserts
-- nodes) never wipes them; prompt_hash says what the text was generated from, so an
-- explanation is reused only while the code and its call context are unchanged.
CREATE TABLE IF NOT EXISTS narrations (
    node_id     TEXT PRIMARY KEY REFERENCES nodes(id),
    prompt_hash TEXT NOT NULL,
    text        TEXT NOT NULL,
    model       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Explanations of a whole call chain. A chain has no single node to hang the text on,
-- so it's keyed by a hash of the exact prompt: same chain, same code, same call
-- details -> same key -> reuse. Any change to any of them is a different key.
CREATE TABLE IF NOT EXISTS path_explanations (
    prompt_hash TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    model       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- A model's documentation review of a function, keyed by a hash of the exact prompt (the
-- code and its call context), so an unchanged function is not reviewed twice.
CREATE TABLE IF NOT EXISTS drift_reviews (
    prompt_hash   TEXT PRIMARY KEY,
    findings_json TEXT NOT NULL,
    model         TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
