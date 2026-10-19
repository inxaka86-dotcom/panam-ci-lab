#!/usr/bin/env python3
"""Durable LOCAL SQLite reservation simulation, never a network/API broker.

PUBLIC SYNTHETIC fixtures and FABRICATED USD tariffs only. There is no model
execution, network/HTTP/socket client, credential access, host management,
provider charging, refund or external execution authority.

SQLite's atomic transactions are tested on temporary local filesystems only;
this does not prove storage durability under arbitrary power loss or adversarial
modification, and it is not a distributed real-billing ledger.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from synthetic_usd_envelope import Invalid, project, DEMO_CAP_MICRO_USD

NONCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,63}\Z")
SCHEMA_VERSION = "panam.leanrea.local-sqlite-simulation.v1"
STATES = frozenset(("HELD", "UNKNOWN_NO_REFUND", "CLAIM_NO_REFUND",
                   "OVERCLAIM_STOP"))
SLOTS = frozenset((c, arm) for c in
                 ("LR-E01", "LR-N01", "LR-G01", "LR-D01")
                 for arm in ("base", "leanrea"))


def canonical_digest(packet: dict) -> str:
    try:
        data = json.dumps(packet, sort_keys=True, ensure_ascii=True,
                          separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise Invalid("Invalid synthetic envelope") from exc
    return sha256(data.encode("ascii")).hexdigest()


def require_local_path(path: Path, new: bool) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or path.name in (".", ".."):
        raise Invalid("Explicit absolute SQLite path required")
    parent = path.parent
    try:
        info = parent.lstat()
    except OSError as exc:
        raise Invalid("Missing disposable directory") from exc
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise Invalid("Disposable parent must be owned and mode 0700")
    if path.is_symlink():
        raise Invalid("Symlinked DB path is forbidden")
    if new:
        if path.exists():
            raise Invalid("Will not overwrite existing SQLite file")
    else:
        try:
            meta = path.lstat()
        except OSError as exc:
            raise Invalid("Existing SQLite file missing") from exc
        if (not stat.S_ISREG(meta.st_mode) or
                stat.S_IMODE(meta.st_mode) != 0o600 or
                meta.st_uid != os.getuid() or meta.st_nlink != 1):
            raise Invalid("Existing database file ownership/mode/links unsafe")
    return path


class SyntheticSQLiteLedger:
    """8-slot, local-only, no-external-send accounting demo; no refunds."""

    def __init__(self, example_envelope: dict, path: Path, *, create: bool):
        report = project(example_envelope)
        if not report["synthetic_arithmetic_under_demo_cap"]:
            raise Invalid("Synthetic envelope cannot fit within toy ceiling")
        self._costs = {
            (v["case_id"], v["arm"]): v["synthetic_worst_case_micro_usd"]
            for v in report["per_slot"]
        }
        if set(self._costs) != SLOTS:
            raise Invalid("Unexpected synthetic slot set")
        self._binding = canonical_digest(example_envelope)
        self._path = require_local_path(path, new=create)
        if create:
            try:
                fd = os.open(self._path, os.O_CREAT | os.O_EXCL |
                             os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
                os.close(fd)
            except OSError as exc:
                raise Invalid("Unsafe or concurrent SQLite create") from exc
            with self._open_unverified() as c:
                try:
                    c.execute("BEGIN IMMEDIATE")
                    c.execute("CREATE TABLE metadata (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
                    c.execute("""
                        CREATE TABLE reservations (
                            case_id TEXT NOT NULL, arm TEXT NOT NULL,
                            nonce TEXT NOT NULL UNIQUE,
                            reserved_micro_usd INTEGER NOT NULL,
                            state TEXT NOT NULL, claim_micro_usd INTEGER,
                            PRIMARY KEY(case_id, arm)
                        )
                    """)
                    c.executemany("INSERT INTO metadata (k,v) VALUES (?,?)", (
                        ("schema", SCHEMA_VERSION), ("envelope_sha256", self._binding),
                        ("stopped", "0"),
                    ))
                    c.execute("PRAGMA user_version=1")
                    c.execute("COMMIT")
                except Exception:
                    if c.in_transaction:
                        c.execute("ROLLBACK")
                    # Keep incomplete DB as a visible, safely-blocked artifact.
                    raise
        # An interrupted initialization, tampering or mismatched manifest
        # must refuse any subsequent reservation rather than reinitialize.
        with self._txn() as c:
            self._validate(c)

    @contextmanager
    def _open_unverified(self):
        require_local_path(self._path, new=False)
        try:
            conn = sqlite3.connect(str(self._path), timeout=3,
                                   isolation_level=None)
            conn.execute("PRAGMA busy_timeout=3000")
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=FULL")
            try:
                yield conn
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise Invalid("SQLite unavailable or corrupted") from exc

    @contextmanager
    def _txn(self):
        with self._open_unverified() as c:
            try:
                c.execute("BEGIN IMMEDIATE")
                self._validate(c)
                yield c
                c.execute("COMMIT")
            except Exception:
                if c.in_transaction:
                    c.execute("ROLLBACK")
                raise

    def _validate(self, conn):
        if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise Invalid("SQLite integrity check failed")
        if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise Invalid("Unrecognized DB schema version")
        try:
            pairs = conn.execute("SELECT k,v FROM metadata ORDER BY k").fetchall()
        except sqlite3.Error as exc:
            raise Invalid("Invalid database metadata") from exc
        meta = dict(pairs)
        if (len(pairs) != 3 or meta.get("schema") != SCHEMA_VERSION
                or meta.get("envelope_sha256") != self._binding
                or meta.get("stopped") not in ("0", "1")):
            raise Invalid("DB envelope or stop metadata mismatch")
        try:
            rows = conn.execute(
                "SELECT case_id, arm, nonce, reserved_micro_usd, state,"
                " claim_micro_usd FROM reservations"
            ).fetchall()
        except sqlite3.Error as exc:
            raise Invalid("Invalid reservation schema") from exc
        if len(rows) > 8:
            raise Invalid("Unexpected reservation count")
        held = 0
        for case, arm, nonce, amount, state, claimed in rows:
            if ((case, arm) not in self._costs
                    or amount != self._costs[(case, arm)]
                    or not isinstance(nonce, str) or not NONCE.fullmatch(nonce)
                    or state not in STATES
                    or (claimed is not None and (
                        type(claimed) is not int or claimed < 0
                        or (state != "OVERCLAIM_STOP" and claimed > amount)))
                    or (claimed is None and state in
                        ("CLAIM_NO_REFUND", "OVERCLAIM_STOP"))
                    or (state in ("HELD", "UNKNOWN_NO_REFUND")
                        and claimed is not None)):
                raise Invalid("Untrusted reservation contents")
            held += amount
        if held > DEMO_CAP_MICRO_USD:
            raise Invalid("Synthetic DB would exceed toy ceiling")
        if any(s == "OVERCLAIM_STOP" for *_, s, claimed in rows) and meta["stopped"] != "1":
            raise Invalid("Overclaim must permanently stop book")

    @staticmethod
    def _valid_slot(case: str, arm: str):
        if not isinstance(case, str) or not isinstance(arm, str) or (case, arm) not in SLOTS:
            raise Invalid("Unexpected or malformed A/B slot")

    def reserve(self, case: str, arm: str, nonce: str) -> dict:
        self._valid_slot(case, arm)
        if not isinstance(nonce, str) or not NONCE.fullmatch(nonce):
            raise Invalid("Invalid nonce")
        with self._txn() as c:
            if c.execute("SELECT v FROM metadata WHERE k='stopped'").fetchone()[0] != "0":
                raise Invalid("Ledger stopped")
            if c.execute("SELECT 1 FROM reservations WHERE case_id=? AND arm=?",
                         (case, arm)).fetchone():
                raise Invalid("Duplicate slot")
            if c.execute("SELECT 1 FROM reservations WHERE nonce=?", (nonce,)).fetchone():
                raise Invalid("Nonce replay")
            held = c.execute(
                "SELECT COALESCE(SUM(reserved_micro_usd),0) FROM reservations"
            ).fetchone()[0]
            amount = self._costs[(case, arm)]
            if held + amount > DEMO_CAP_MICRO_USD:
                raise Invalid("Toy ceiling exceeded")
            c.execute("""
                INSERT INTO reservations
                (case_id,arm,nonce,reserved_micro_usd,state,claim_micro_usd)
                VALUES(?,?,?,?,?,NULL)
            """, (case, arm, nonce, amount, "HELD"))
        return {
            "case_id": case, "arm": arm,
            "synthetic_reserved_micro_usd": amount,
            "synthetic_reservation_recorded": True,
            "real_upstream_request_allowed": False,
            "provider_call_performed": False,
            "specific_owner_spend_approval": False,
        }

    def uncertain(self, case: str, arm: str) -> None:
        self._valid_slot(case, arm)
        with self._txn() as c:
            change = c.execute("""
                UPDATE reservations SET state='UNKNOWN_NO_REFUND'
                WHERE case_id=? AND arm=? AND state='HELD'
            """, (case, arm))
            if change.rowcount != 1:
                raise Invalid("Not a held synthetic slot")

    def claim(self, case: str, arm: str, claimed_micro_usd: int) -> None:
        self._valid_slot(case, arm)
        if type(claimed_micro_usd) is not int or claimed_micro_usd < 0:
            raise Invalid("Invalid synthetic claim")
        exceeded = False
        with self._txn() as c:
            existing = c.execute("""
                SELECT reserved_micro_usd FROM reservations
                WHERE case_id=? AND arm=? AND state='HELD'
            """, (case, arm)).fetchone()
            if existing is None:
                raise Invalid("No held reservation")
            exceeded = claimed_micro_usd > existing[0]
            c.execute("""
                UPDATE reservations SET state=?, claim_micro_usd=?
                WHERE case_id=? AND arm=?
            """, ("OVERCLAIM_STOP" if exceeded else "CLAIM_NO_REFUND",
                  claimed_micro_usd, case, arm))
            if exceeded:
                c.execute("UPDATE metadata SET v='1' WHERE k='stopped'")
        if exceeded:
            raise Invalid("Overclaim recorded and ledger stopped (no refund)")

    def stop(self) -> None:
        with self._txn() as c:
            c.execute("UPDATE metadata SET v='1' WHERE k='stopped'")

    def snapshot(self) -> dict:
        with self._txn() as c:
            rows = c.execute("""
                SELECT case_id, arm, state, reserved_micro_usd
                FROM reservations ORDER BY case_id,arm
            """).fetchall()
            stopped = c.execute("SELECT v FROM metadata WHERE k='stopped'").fetchone()[0]
        return {
            "schema": "panam.leanrea.sqlite-demo-snapshot.v1",
            "slots_reserved": len(rows),
            "synthetic_held_micro_usd": sum(v[3] for v in rows),
            "toy_cap_micro_usd": DEMO_CAP_MICRO_USD,
            "stopped": stopped == "1",
            "states": [{"case_id": a, "arm": b, "state": state}
                       for a, b, state, amount in rows],
            "sqlite_atomic_transactions_demonstrated": True,
            "provider_billable_request_executed": False,
            "real_upstream_request_allowed": False,
            "real_usd_hard_cap_enforced": False,
            "currency_contract_verified": False,
            "provider_charges_verified": False,
            "crash_consistency_on_target_host_verified": False,
            "kernel_network_isolation_verified": False,
            "authenticated_model_response_verified": False,
            "owner_spend_approval": False,
            "status": "LOCAL_SQLITE_SYNTHETIC_ONLY_NOT_A_BROKER",
        }
