"""Synthetic-only PANAM SIGNAL v1 demonstration. No network, Reddrix or Reddit calls."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import json
import re

EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)")
PATH = re.compile(r"/discussions/[A-Za-z0-9_-]{1,100}/?")
TOPICS = {
    "contracts": ("договор", "контракт", "contract"),
    "consumer": ("возврат", "гаранти", "refund"),
    "procurement": ("закупк", "торг", "поставщик"),
    "employment": ("зарплат", "увольнен"),
    "housing": ("аренд", "ипотек"),
}
SCHEMA = "panam.signal.v1"


class Rejected(ValueError):
    """Input is outside the synthetic offline contract."""


def timestamp(raw: str) -> datetime:
    if not isinstance(raw, str):
        raise Rejected("timestamp must be a string")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None:
            raise ValueError("missing offset")
        return value.astimezone(timezone.utc)
    except ValueError as exc:
        raise Rejected("invalid timestamp") from exc


def isotime(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def safe_url(raw: str, allowed_host: str) -> str:
    if not isinstance(raw, str) or len(raw) > 2048 or any(ord(c) < 32 for c in raw):
        raise Rejected("invalid URL")
    try:
        parsed = urlsplit(raw)
        host, port = parsed.hostname, parsed.port
    except ValueError as exc:
        raise Rejected("malformed URL") from exc
    if (parsed.scheme != "https" or host != allowed_host or port is not None
            or parsed.username or parsed.password or parsed.fragment):
        raise Rejected("URL outside exact HTTPS source allowlist")
    if not PATH.fullmatch(parsed.path):
        raise Rejected("invalid discussion path")
    return urlunsplit(("https", host, parsed.path, "", ""))


def redact(value: str | None, cap: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > 16000:
        raise Rejected("invalid text field")
    value = unescape(value)
    return PHONE.sub("[PHONE]", EMAIL.sub("[EMAIL]", value))[:cap].strip()


def validate_policy(policy: dict) -> dict:
    if not isinstance(policy, dict):
        raise Rejected("invalid policy")
    if (policy.get("mode") != "offline_fixture_only"
            or policy.get("data_status") != "synthetic"
            or policy.get("authorization") != "locally_authored_synthetic_fixture"):
        raise Rejected("real sources prohibited")
    if policy.get("allowed_host") != "forum.example.org":
        raise Rejected("only reserved synthetic hostname supported")
    if policy.get("source_id") != "synthetic_legal_discussions":
        raise Rejected("unexpected source_id")
    if type(policy.get("max_records")) is not int or not 1 <= policy["max_records"] <= 100:
        raise Rejected("invalid record limit")
    if type(policy.get("retention_days")) is not int or not 1 <= policy["retention_days"] <= 30:
        raise Rejected("invalid retention")
    return policy


def normalize(record: dict, policy: dict, captured_at: str) -> dict:
    policy = validate_policy(policy)
    if not isinstance(record, dict) or record.get("synthetic_fixture") is not True:
        raise Rejected("synthetic flag required")
    if record.get("source_id") != policy["source_id"]:
        raise Rejected("source mismatch")
    rid, kind = record.get("record_id"), record.get("kind")
    if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", rid):
        raise Rejected("invalid record id")
    if kind not in ("post", "comment", "discussion"):
        raise Rejected("invalid kind")
    url = safe_url(record.get("url"), policy["allowed_host"])
    published = isotime(timestamp(record.get("published_at")))
    captured = timestamp(captured_at)
    title = redact(record.get("title"), 250)
    body = redact(record.get("body"), 3000)
    if not (title or body):
        raise Rejected("empty text")
    content = (title + " " + body).lower()
    return {
        "schema": SCHEMA,
        "record_key": sha256(f"{policy['source_id']}:{kind}:{rid}".encode()).hexdigest()[:24],
        "source_id": policy["source_id"], "source_url": url, "type": kind,
        "published_at": published, "captured_at": isotime(captured),
        "delete_after": isotime(captured + timedelta(days=policy["retention_days"])),
        "title": title, "body": body,
        "topics": sorted(label for label, needles in TOPICS.items()
                         if any(needle in content for needle in needles)),
        "provenance": {"kind": "synthetic_fixture", "document_ref": "PANAM-OFFLINE-2026-10-20"},
    }


def process_fixture(path: Path, root: Path, policy: dict, captured_at: str) -> tuple[list[dict], dict]:
    policy = validate_policy(policy)
    root = Path(root).resolve(strict=True)
    path = Path(path).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file() or path.suffix != ".jsonl":
        raise Rejected("fixture file outside root")
    if path.stat().st_size > 512000:
        raise Rejected("fixture file too large")
    records, seen, count, duplicates = [], set(), 0, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if len(line.encode("utf-8")) > 16384:
            raise Rejected("fixture line too large")
        count += 1
        if count > policy["max_records"]:
            raise Rejected("record limit exceeded")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise Rejected("malformed fixture") from exc
        event = normalize(record, policy, captured_at)
        if event["record_key"] in seen:
            duplicates += 1
        else:
            seen.add(event["record_key"])
            records.append(event)
    counts = Counter(t for event in records for t in event["topics"])
    report = {"schema": "panam.signal.report.v1", "mode": "synthetic_offline_only",
              "consumed": count, "accepted": len(records), "duplicates": duplicates,
              "topics": dict(sorted(counts.items()))}
    return records, report
