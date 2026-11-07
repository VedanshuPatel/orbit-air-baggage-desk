import sqlite3
from datetime import datetime, timedelta

import pytest

import claims
from tests.conftest import T0


def _file(conn, **overrides):
    fields = {
        "passenger": "Amina Shah",
        "flight": "OA101",
        "claim_type": "delayed",
        "tier": "gold",
        "note": "Bag still in transit",
        "now": T0,
        "by": "veda",
    }
    fields.update(overrides)
    return claims.file_claim(conn, **fields)


def test_init_db_creates_tables(conn):
    names = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"claims", "history"} <= names


def test_file_claim_stores_open_claim(conn):
    claim_id = _file(conn)
    row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
    assert row["id"] == claim_id
    assert row["passenger"] == "Amina Shah"
    assert row["flight"] == "OA101"
    assert row["type"] == "delayed"
    assert row["tier"] == "gold"
    assert row["status"] == "open"
    assert row["agent"] is None
    assert row["note"] == "Bag still in transit"
    assert row["filed_at"] == "2026-11-02T08:00:00"
    assert row["deadline"] == "2026-11-02T12:00:00"


@pytest.mark.parametrize("passenger", ["", "   "])
def test_blank_passenger_is_rejected(conn, passenger):
    with pytest.raises(claims.ClaimError, match="[Pp]assenger"):
        _file(conn, passenger=passenger)
    assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0


def test_blank_flight_is_rejected(conn):
    with pytest.raises(claims.ClaimError, match="[Ff]light"):
        _file(conn, flight="  ")
    assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0


def test_unknown_type_is_rejected(conn):
    with pytest.raises(claims.ClaimError, match="delayed"):
        _file(conn, claim_type="missing")
    assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0


def test_unknown_tier_is_rejected(conn):
    with pytest.raises(claims.ClaimError, match="gold"):
        _file(conn, tier="platinum")
    assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("tier", "hours"),
    [("gold", 4), ("silver", 24), ("standard", 72)],
)
def test_deadline_matches_tier(conn, tier, hours):
    claim_id = _file(conn, tier=tier)
    row = conn.execute(
        "SELECT filed_at, deadline FROM claims WHERE id = ?", (claim_id,)
    ).fetchone()
    filed_at = datetime.fromisoformat(row["filed_at"])
    deadline = datetime.fromisoformat(row["deadline"])
    assert deadline - filed_at == timedelta(hours=hours)


@pytest.mark.parametrize(
    ("column", "bad_value"),
    [("type", "stolen"), ("tier", "bronze"), ("status", "pending")],
)
def test_check_constraint_rejects_bad_value(conn, column, bad_value):
    values = {
        "passenger": "Amina Shah",
        "flight": "OA101",
        "type": "lost",
        "tier": "silver",
        "status": "open",
        "filed_at": "2026-11-02T08:00:00",
        "deadline": "2026-11-03T08:00:00",
    }
    values[column] = bad_value
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO claims (passenger, flight, type, tier, status, filed_at, deadline)
            VALUES (:passenger, :flight, :type, :tier, :status, :filed_at, :deadline)
            """,
            values,
        )


def test_filing_writes_first_history_entry(conn):
    claim_id = _file(conn)
    rows = conn.execute(
        "SELECT * FROM history WHERE claim_id = ? ORDER BY id", (claim_id,)
    ).fetchall()
    assert len(rows) == 1
    entry = rows[0]
    assert entry["old_status"] is None
    assert entry["new_status"] == "open"
    assert entry["changed_by"] == "veda"
    assert entry["changed_at"] == "2026-11-02T08:00:00"


def test_list_claims_filters_by_status_and_tier(conn):
    gold_id = _file(conn, tier="gold", flight="OA101")
    silver_id = _file(conn, tier="silver", flight="OA202", claim_type="lost")
    standard_id = _file(conn, tier="standard", flight="OA303", claim_type="damaged")
    conn.execute("UPDATE claims SET status = 'assigned' WHERE id = ?", (standard_id,))
    conn.commit()

    open_ids = {row["id"] for row in claims.list_claims(conn, status="open")}
    gold_ids = [row["id"] for row in claims.list_claims(conn, tier="gold")]
    both_ids = [row["id"] for row in claims.list_claims(conn, status="open", tier="gold")]

    assert open_ids == {gold_id, silver_id}
    assert gold_ids == [gold_id]
    assert both_ids == [gold_id]
