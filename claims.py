from datetime import datetime, timedelta

CLAIM_TYPES = ("delayed", "lost", "damaged")
TIERS = ("standard", "silver", "gold")
STATUSES = ("open", "assigned", "escalated", "resolved", "closed")
DEADLINE_HOURS = {"gold": 4, "silver": 24, "standard": 72}
ALLOWED_CHANGES = {
    "open": {"assigned", "escalated"},
    "assigned": {"resolved", "escalated"},
    "escalated": {"assigned", "resolved"},
    "resolved": {"closed"},
    "closed": set(),
}


class ClaimError(Exception):
    pass


def file_claim(conn, passenger, flight, claim_type, tier, note, now, by):
    passenger = _required_text(passenger, "Passenger name")
    flight = _required_text(flight, "Flight number")
    _one_of(claim_type, CLAIM_TYPES, "type")
    _one_of(tier, TIERS, "tier")
    filed_at = _as_naive_datetime(now)
    deadline = filed_at + timedelta(hours=DEADLINE_HOURS[tier])
    filed_text = filed_at.isoformat(timespec="seconds")
    deadline_text = deadline.isoformat(timespec="seconds")
    note_text = "" if note is None else str(note)

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO claims (passenger, flight, type, tier, note, filed_at, deadline)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (passenger, flight, claim_type, tier, note_text, filed_text, deadline_text),
        )
        claim_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO history (claim_id, old_status, new_status, changed_by, changed_at)
            VALUES (?, NULL, 'open', ?, ?)
            """,
            (claim_id, by, filed_text),
        )
    return claim_id


def assign_claim(conn, claim_id, agent, now, by):
    agent_name = _required_text(agent, "Agent name")
    _change_status(conn, claim_id, "assigned", now, by, agent=agent_name)


def resolve_claim(conn, claim_id, now, by):
    _change_status(conn, claim_id, "resolved", now, by)


def close_claim(conn, claim_id, now, by):
    _change_status(conn, claim_id, "closed", now, by)


def is_overdue(deadline, now):
    return _as_naive_datetime(now) > _as_naive_datetime(deadline)


def escalate_overdue(conn, now, by="system"):
    rows = conn.execute(
        """
        SELECT id, deadline FROM claims
        WHERE status IN ('open', 'assigned')
        ORDER BY id
        """
    ).fetchall()
    escalated = []
    for row in rows:
        if is_overdue(row["deadline"], now):
            _change_status(conn, row["id"], "escalated", now, by)
            escalated.append(row["id"])
    return escalated


def seed_claims(conn, rows, now, by="seed"):
    prepared = []
    for index, row in enumerate(rows, start=1):
        try:
            passenger = _required_text(row.get("passenger"), "Passenger name")
            flight = _required_text(row.get("flight"), "Flight number")
            claim_type = row.get("type")
            tier = row.get("tier")
            _one_of(claim_type, CLAIM_TYPES, "type")
            _one_of(tier, TIERS, "tier")
            note = "" if row.get("note") is None else str(row.get("note"))
        except ClaimError as exc:
            raise ClaimError(f"Row {index + 1}: {exc}") from exc
        prepared.append((passenger, flight, claim_type, tier, note))
    return [
        file_claim(conn, passenger, flight, claim_type, tier, note, now, by)
        for passenger, flight, claim_type, tier, note in prepared
    ]


def get_history(conn, claim_id):
    _get_claim(conn, claim_id)
    return conn.execute(
        "SELECT * FROM history WHERE claim_id = ? ORDER BY id",
        (claim_id,),
    ).fetchall()


def list_claims(conn, status=None, tier=None):
    clauses = []
    params = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if tier is not None:
        clauses.append("tier = ?")
        params.append(tier)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return conn.execute(f"SELECT * FROM claims {where} ORDER BY id", params).fetchall()


def _change_status(conn, claim_id, new_status, now, by, agent=None):
    claim = _get_claim(conn, claim_id)
    current = claim["status"]
    if new_status not in ALLOWED_CHANGES[current]:
        allowed = sorted(ALLOWED_CHANGES[current])
        if allowed:
            raise ClaimError(
                f"Cannot change status from {current} to {new_status}. "
                f"Allowed: {', '.join(allowed)}."
            )
        raise ClaimError(f"Cannot change status from {current}. Nothing is allowed.")
    if new_status == "escalated" and not is_overdue(claim["deadline"], now):
        raise ClaimError("Claim is not overdue, so it cannot be escalated.")
    changed_at = _as_naive_datetime(now).isoformat(timespec="seconds")
    with conn:
        if agent is None:
            conn.execute(
                "UPDATE claims SET status = ? WHERE id = ?",
                (new_status, claim_id),
            )
        else:
            conn.execute(
                "UPDATE claims SET status = ?, agent = ? WHERE id = ?",
                (new_status, agent, claim_id),
            )
        conn.execute(
            """
            INSERT INTO history (claim_id, old_status, new_status, changed_by, changed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (claim_id, current, new_status, by, changed_at),
        )


def _get_claim(conn, claim_id):
    row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if row is None:
        raise ClaimError(f"No claim with id {claim_id}.")
    return row


def _required_text(value, label):
    text = "" if value is None else str(value).strip()
    if not text:
        raise ClaimError(f"{label} cannot be blank.")
    return text


def _one_of(value, allowed, label):
    if value not in allowed:
        choices = ", ".join(allowed)
        raise ClaimError(f"Unknown {label} '{value}'. Choose one of: {choices}.")


def _as_naive_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ClaimError(f"Invalid timestamp '{value}'.") from exc
    if parsed.tzinfo is not None:
        raise ClaimError("Timestamp must not include a timezone.")
    return parsed.replace(microsecond=0)
