from datetime import datetime, timedelta

CLAIM_TYPES = ("delayed", "lost", "damaged")
TIERS = ("standard", "silver", "gold")
STATUSES = ("open", "assigned", "escalated", "resolved", "closed")
DEADLINE_HOURS = {"gold": 4, "silver": 24, "standard": 72}


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
