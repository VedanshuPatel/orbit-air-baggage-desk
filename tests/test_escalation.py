import sqlite3
from datetime import timedelta

import pytest

import claims
from tests.conftest import T0

DEADLINE = T0 + timedelta(hours=4)
MINUTE = timedelta(minutes=1)


def _file(conn, tier="gold"):
    return claims.file_claim(
        conn,
        passenger="Amina Shah",
        flight="OA101",
        claim_type="delayed",
        tier=tier,
        note="",
        now=T0,
        by="veda",
    )


def _claim(conn, claim_id):
    return conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()


def _fail_history_inserts(conn):
    conn.execute(
        """
        CREATE TRIGGER fail_history BEFORE INSERT ON history
        BEGIN
            SELECT RAISE(ABORT, 'history insert failed');
        END
        """
    )


def test_not_overdue_one_minute_before_deadline():
    assert claims.is_overdue(DEADLINE, DEADLINE - MINUTE) is False


def test_not_overdue_exactly_at_deadline():
    assert claims.is_overdue(DEADLINE, DEADLINE) is False


def test_overdue_one_minute_after_deadline():
    assert claims.is_overdue(DEADLINE, DEADLINE + MINUTE) is True


def test_escalate_overdue_open_and_assigned_claims(conn):
    open_id = _file(conn, tier="gold")
    assigned_id = _file(conn, tier="gold")
    claims.assign_claim(conn, assigned_id, "Priya", T0 + MINUTE, "mira")
    _file(conn, tier="standard")

    escalated = claims.escalate_overdue(conn, DEADLINE + MINUTE)

    assert escalated == [open_id, assigned_id]
    assert _claim(conn, open_id)["status"] == "escalated"
    assert _claim(conn, assigned_id)["status"] == "escalated"


def test_claims_not_yet_overdue_are_left_alone(conn):
    claim_id = _file(conn, tier="gold")
    escalated = claims.escalate_overdue(conn, DEADLINE - MINUTE)
    assert escalated == []
    assert _claim(conn, claim_id)["status"] == "open"


def test_resolved_and_closed_claims_are_left_alone(conn):
    resolved_id = _file(conn, tier="gold")
    closed_id = _file(conn, tier="gold")
    claims.assign_claim(conn, resolved_id, "Priya", T0 + MINUTE, "mira")
    claims.resolve_claim(conn, resolved_id, T0 + MINUTE, "mira")
    claims.assign_claim(conn, closed_id, "Priya", T0 + MINUTE, "mira")
    claims.resolve_claim(conn, closed_id, T0 + MINUTE, "mira")
    claims.close_claim(conn, closed_id, T0 + MINUTE, "mira")

    escalated = claims.escalate_overdue(conn, DEADLINE + MINUTE)

    assert escalated == []
    assert _claim(conn, resolved_id)["status"] == "resolved"
    assert _claim(conn, closed_id)["status"] == "closed"


def test_already_escalated_claim_is_not_escalated_again(conn):
    claim_id = _file(conn, tier="gold")
    first = claims.escalate_overdue(conn, DEADLINE + MINUTE)
    history_count = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    second = claims.escalate_overdue(conn, DEADLINE + MINUTE)

    assert first == [claim_id]
    assert second == []
    assert _claim(conn, claim_id)["status"] == "escalated"
    assert conn.execute("SELECT COUNT(*) FROM history").fetchone()[0] == history_count


def test_escalation_writes_history(conn):
    claim_id = _file(conn, tier="gold")
    claims.assign_claim(conn, claim_id, "Priya", T0 + MINUTE, "mira")
    when = DEADLINE + MINUTE
    claims.escalate_overdue(conn, when)

    row = conn.execute(
        """
        SELECT old_status, new_status, changed_by, changed_at
        FROM history WHERE claim_id = ? ORDER BY id DESC LIMIT 1
        """,
        (claim_id,),
    ).fetchone()
    assert tuple(row) == ("assigned", "escalated", "system", "2026-11-02T12:01:00")


def test_status_change_rolls_back_when_history_insert_fails(conn):
    claim_id = _file(conn)
    _fail_history_inserts(conn)
    with pytest.raises(sqlite3.IntegrityError):
        claims.assign_claim(conn, claim_id, "Priya", T0 + MINUTE, "mira")
    assert _claim(conn, claim_id)["status"] == "open"
    assert conn.execute(
        "SELECT COUNT(*) FROM history WHERE claim_id = ?", (claim_id,)
    ).fetchone()[0] == 1


def test_filing_rolls_back_when_history_insert_fails(conn):
    _fail_history_inserts(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _file(conn)
    assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 0
