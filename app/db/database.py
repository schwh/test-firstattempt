# -------------------------------------------------------------------
# database.py — Sets up and manages the SQLite database.
#
# We use Python's built-in sqlite3 module. No extra packages needed.
# SQLite stores everything in a single file (diamond_hands.db).
#
# KEY CONCEPT: Every function that changes data (INSERT, UPDATE, DELETE)
# must call conn.commit() to save the change permanently.
# -------------------------------------------------------------------

import sqlite3
from app.config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    """
    Open a connection to the database.

    row_factory = sqlite3.Row means query results come back as
    dict-like objects instead of plain tuples, so you can do
    row["name"] instead of row[0]. Much easier to read.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    # Enable foreign key enforcement (off by default in SQLite)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables():
    """
    Create all the database tables if they don't exist yet.

    This runs once when the server starts. If the tables already
    exist, the IF NOT EXISTS clause means nothing happens.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # ---- Players: the MLB athletes you can trade shares of ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            team        TEXT    NOT NULL,
            position    TEXT    NOT NULL,
            batting_avg REAL,           -- e.g. 0.304 (NULL for pitchers)
            home_runs   INTEGER,        -- e.g. 54
            rbi         INTEGER,        -- runs batted in
            era         REAL,           -- earned run average (NULL for batters)
            wins        INTEGER,        -- pitcher wins
            strikeouts  INTEGER,        -- pitcher strikeouts
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ---- Users: people who trade on the platform ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    NOT NULL UNIQUE,
            balance     REAL    NOT NULL DEFAULT 10000.0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ---- Holdings: how many shares each user owns of each player ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL REFERENCES users(id),
            player_id      INTEGER NOT NULL REFERENCES players(id),
            shares         INTEGER NOT NULL DEFAULT 0,
            avg_cost_basis REAL    NOT NULL DEFAULT 0.0,
            UNIQUE(user_id, player_id)
        )
    """)

    # ---- AMM Pools: the automated market maker's liquidity for each player ----
    # Think of this as a "pool" containing some shares and some cash.
    # The ratio of cash to shares determines the price.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS amm_pools (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id        INTEGER NOT NULL UNIQUE REFERENCES players(id),
            token_reserve    REAL    NOT NULL,  -- shares in the pool
            currency_reserve REAL    NOT NULL,  -- fantasy dollars in the pool
            created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ---- Orders: limit orders placed by users ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES users(id),
            player_id       INTEGER NOT NULL REFERENCES players(id),
            side            TEXT    NOT NULL CHECK(side IN ('buy', 'sell')),
            price           REAL    NOT NULL,
            quantity         INTEGER NOT NULL,
            filled_quantity  INTEGER NOT NULL DEFAULT 0,
            status          TEXT    NOT NULL DEFAULT 'open'
                            CHECK(status IN ('open', 'filled', 'partial', 'cancelled')),
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ---- Trades: every executed trade (for history) ----
    # buyer_id and seller_id can be NULL when the AMM is the counterparty
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id    INTEGER REFERENCES users(id),   -- NULL if AMM bought
            seller_id   INTEGER REFERENCES users(id),   -- NULL if AMM sold
            player_id   INTEGER NOT NULL REFERENCES players(id),
            price       REAL    NOT NULL,
            quantity    INTEGER NOT NULL,
            trade_type  TEXT    NOT NULL,  -- 'market', 'limit', 'amm'
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ---- Price History: snapshots of player prices over time ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id   INTEGER NOT NULL REFERENCES players(id),
            price       REAL    NOT NULL,
            source      TEXT    NOT NULL,  -- 'amm', 'trade', 'snapshot'
            recorded_at TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()
    print("Database tables created successfully.")
