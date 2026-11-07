import sqlite3

_TYPES = "'delayed', 'lost', 'damaged'"
_TIERS = "'standard', 'silver', 'gold'"
_STATUSES = "'open', 'assigned', 'escalated', 'resolved', 'closed'"


def connect(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(connection):
    connection.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            passenger TEXT NOT NULL CHECK (trim(passenger) <> ''),
            flight TEXT NOT NULL CHECK (trim(flight) <> ''),
            type TEXT NOT NULL CHECK (type IN ({_TYPES})),
            tier TEXT NOT NULL CHECK (tier IN ({_TIERS})),
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ({_STATUSES})),
            agent TEXT,
            note TEXT NOT NULL DEFAULT '',
            filed_at TEXT NOT NULL,
            deadline TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id INTEGER NOT NULL REFERENCES claims (id),
            old_status TEXT CHECK (old_status IS NULL OR old_status IN ({_STATUSES})),
            new_status TEXT NOT NULL CHECK (new_status IN ({_STATUSES})),
            changed_by TEXT NOT NULL,
            changed_at TEXT NOT NULL
        );
        """
    )
    connection.commit()
