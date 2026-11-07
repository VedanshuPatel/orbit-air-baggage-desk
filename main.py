import argparse
import csv
from datetime import datetime

import claims
import db


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        now = _current_time(args.now)
        connection = db.connect(args.db)
        db.init_db(connection)
        try:
            _run(args, connection, now)
        finally:
            connection.close()
    except claims.ClaimError as exc:
        print(f"Error: {exc}")
        return 1
    return 0


def _parser():
    parser = argparse.ArgumentParser(prog="main.py")
    parser.add_argument("--now", help="ISO timestamp used instead of the real clock")
    parser.add_argument("--db", default="baggage.db", help="SQLite database path")
    commands = parser.add_subparsers(dest="command", required=True)

    file_cmd = commands.add_parser("file")
    file_cmd.add_argument("--passenger", required=True)
    file_cmd.add_argument("--flight", required=True)
    file_cmd.add_argument("--type", required=True, dest="claim_type")
    file_cmd.add_argument("--tier", required=True)
    file_cmd.add_argument("--note", default="")
    file_cmd.add_argument("--by", default="desk")

    list_cmd = commands.add_parser("list")
    list_cmd.add_argument("--status")
    list_cmd.add_argument("--tier")

    assign_cmd = commands.add_parser("assign")
    assign_cmd.add_argument("claim_id", type=int)
    assign_cmd.add_argument("agent")
    assign_cmd.add_argument("--by", default="desk")

    resolve_cmd = commands.add_parser("resolve")
    resolve_cmd.add_argument("claim_id", type=int)
    resolve_cmd.add_argument("--by", default="desk")

    close_cmd = commands.add_parser("close")
    close_cmd.add_argument("claim_id", type=int)
    close_cmd.add_argument("--by", default="desk")

    escalate_cmd = commands.add_parser("escalate")
    escalate_cmd.add_argument("--by", default="system")

    history_cmd = commands.add_parser("history")
    history_cmd.add_argument("claim_id", type=int)

    seed_cmd = commands.add_parser("seed")
    seed_cmd.add_argument("csv_path")
    return parser


def _run(args, connection, now):
    if args.command == "file":
        claim_id = claims.file_claim(
            connection,
            args.passenger,
            args.flight,
            args.claim_type,
            args.tier,
            args.note,
            now,
            args.by,
        )
        print(f"Filed claim {claim_id}.")
    elif args.command == "list":
        _print_claims(claims.list_claims(connection, status=args.status, tier=args.tier))
    elif args.command == "assign":
        claims.assign_claim(connection, args.claim_id, args.agent, now, args.by)
        print(f"Claim {args.claim_id} assigned to {args.agent}.")
    elif args.command == "resolve":
        claims.resolve_claim(connection, args.claim_id, now, args.by)
        print(f"Claim {args.claim_id} resolved.")
    elif args.command == "close":
        claims.close_claim(connection, args.claim_id, now, args.by)
        print(f"Claim {args.claim_id} closed.")
    elif args.command == "escalate":
        escalated = claims.escalate_overdue(connection, now, by=args.by)
        if escalated:
            ids = ", ".join(str(claim_id) for claim_id in escalated)
            print(f"Escalated claims: {ids}")
        else:
            print("Escalated claims:")
    elif args.command == "history":
        _print_history(claims.get_history(connection, args.claim_id))
    elif args.command == "seed":
        rows = _read_seed_rows(args.csv_path)
        claim_ids = claims.seed_claims(connection, rows, now)
        print(f"Seeded {len(claim_ids)} claims.")


def _print_claims(rows):
    if not rows:
        print("No claims.")
        return
    for row in rows:
        agent = row["agent"] or "-"
        print(
            f"{row['id']}  {row['passenger']}  {row['flight']}  {row['type']}  "
            f"{row['tier']}  {row['status']}  {agent}  {row['note']}"
        )


def _print_history(rows):
    if not rows:
        print("No history.")
        return
    for row in rows:
        old_status = row["old_status"] or "none"
        print(
            f"{old_status} -> {row['new_status']} by {row['changed_by']} at {row['changed_at']}"
        )


def _read_seed_rows(path):
    try:
        handle = open(path, newline="", encoding="utf-8")
    except OSError as exc:
        raise claims.ClaimError(f"Cannot read {path}: {exc.strerror}.") from exc
    with handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = {"passenger", "flight", "type", "tier", "note"} - set(fieldnames)
        if missing:
            names = ", ".join(sorted(missing))
            raise claims.ClaimError(f"Seed file is missing columns: {names}.")
        return list(reader)


def _current_time(text):
    if text is None:
        return datetime.now().replace(microsecond=0)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise claims.ClaimError(f"Invalid timestamp '{text}'.") from exc
    if parsed.tzinfo is not None:
        raise claims.ClaimError("Timestamp must not include a timezone.")
    return parsed.replace(microsecond=0)


if __name__ == "__main__":
    raise SystemExit(main())
