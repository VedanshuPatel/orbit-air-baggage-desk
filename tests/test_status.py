from datetime import timedelta

import pytest

import claims
from tests.conftest import T0

T1 = T0 + timedelta(hours=1)
T2 = T0 + timedelta(hours=2)
T3 = T0 + timedelta(hours=3)


def _file(conn):
    return claims.file_claim(
        conn,
        passenger="Amina Shah",
        flight="OA101",
        claim_type="delayed",
        tier="silver",
        note="",
        now=T0,
        by="veda",
    )


def _set_status(conn, claim_id, status):
    conn.execute("UPDATE claims SET status = ? WHERE id = ?", (status, claim_id))
    conn.commit()


def _claim(conn, claim_id):
    return conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()


def _snapshot(conn):
    claim_rows = [tuple(row) for row in conn.execute("SELECT * FROM claims ORDER BY id")]
    history_rows = [tuple(row) for row in conn.execute("SELECT * FROM history ORDER BY id")]
    return claim_rows, history_rows


def test_assign_open_claim_sets_agent_and_status(conn):
    claim_id = _file(conn)
    claims.assign_claim(conn, claim_id, "Priya", T1, "mira")
    row = _claim(conn, claim_id)
    assert row["status"] == "assigned"
    assert row["agent"] == "Priya"


def test_assign_escalated_claim(conn):
    claim_id = _file(conn)
    _set_status(conn, claim_id, "escalated")
    claims.assign_claim(conn, claim_id, "Priya", T1, "mira")
    row = _claim(conn, claim_id)
    assert row["status"] == "assigned"
    assert row["agent"] == "Priya"


def test_resolve_assigned_claim(conn):
    claim_id = _file(conn)
    claims.assign_claim(conn, claim_id, "Priya", T1, "mira")
    claims.resolve_claim(conn, claim_id, T2, "mira")
    assert _claim(conn, claim_id)["status"] == "resolved"


def test_resolve_escalated_claim(conn):
    claim_id = _file(conn)
    _set_status(conn, claim_id, "escalated")
    claims.resolve_claim(conn, claim_id, T1, "mira")
    assert _claim(conn, claim_id)["status"] == "resolved"


def test_close_resolved_claim(conn):
    claim_id = _file(conn)
    claims.assign_claim(conn, claim_id, "Priya", T1, "mira")
    claims.resolve_claim(conn, claim_id, T2, "mira")
    claims.close_claim(conn, claim_id, T3, "mira")
    assert _claim(conn, claim_id)["status"] == "closed"


def test_close_open_claim_is_rejected(conn):
    claim_id = _file(conn)
    with pytest.raises(claims.ClaimError, match="open"):
        claims.close_claim(conn, claim_id, T1, "mira")
    assert _claim(conn, claim_id)["status"] == "open"


def test_resolve_open_claim_is_rejected(conn):
    claim_id = _file(conn)
    with pytest.raises(claims.ClaimError, match="open"):
        claims.resolve_claim(conn, claim_id, T1, "mira")
    assert _claim(conn, claim_id)["status"] == "open"


@pytest.mark.parametrize("action", ["assign", "resolve", "close"])
def test_closed_claim_cannot_change(conn, action):
    claim_id = _file(conn)
    _set_status(conn, claim_id, "closed")
    with pytest.raises(claims.ClaimError, match="closed"):
        if action == "assign":
            claims.assign_claim(conn, claim_id, "Priya", T1, "mira")
        elif action == "resolve":
            claims.resolve_claim(conn, claim_id, T1, "mira")
        else:
            claims.close_claim(conn, claim_id, T1, "mira")
    assert _claim(conn, claim_id)["status"] == "closed"


@pytest.mark.parametrize("agent", ["", "   "])
def test_blank_agent_is_rejected(conn, agent):
    claim_id = _file(conn)
    before = _snapshot(conn)
    with pytest.raises(claims.ClaimError, match="[Aa]gent"):
        claims.assign_claim(conn, claim_id, agent, T1, "mira")
    assert _snapshot(conn) == before


def test_status_path_writes_history_in_order(conn):
    claim_id = _file(conn)
    claims.assign_claim(conn, claim_id, "Priya", T1, "mira")
    claims.resolve_claim(conn, claim_id, T2, "mira")
    claims.close_claim(conn, claim_id, T3, "mira")
    rows = conn.execute(
        """
        SELECT old_status, new_status, changed_by, changed_at
        FROM history WHERE claim_id = ? ORDER BY id
        """,
        (claim_id,),
    ).fetchall()
    assert [tuple(row) for row in rows] == [
        (None, "open", "veda", "2026-11-02T08:00:00"),
        ("open", "assigned", "mira", "2026-11-02T09:00:00"),
        ("assigned", "resolved", "mira", "2026-11-02T10:00:00"),
        ("resolved", "closed", "mira", "2026-11-02T11:00:00"),
    ]


def test_rejected_or_unknown_change_leaves_tables_unchanged(conn):
    claim_id = _file(conn)
    before = _snapshot(conn)
    with pytest.raises(claims.ClaimError, match="open"):
        claims.close_claim(conn, claim_id, T1, "mira")
    assert _snapshot(conn) == before
    with pytest.raises(claims.ClaimError, match="999"):
        claims.assign_claim(conn, 999, "Priya", T1, "mira")
    assert _snapshot(conn) == before
