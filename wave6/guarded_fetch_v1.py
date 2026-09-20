#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import ipaddress
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Iterable
from urllib.parse import urljoin

from destination_guard_v1 import DestinationGuardError, DestinationVerdict, validate_public_https_url


class TransportSafetyError(RuntimeError):
    pass


class TransportError(RuntimeError):
    pass


@dataclass
class FetchOutcome:
    final_url: str
    status_code: int
    content_type: str
    body: bytes
    redirect_count: int
    downloaded_bytes: int
    contacted_host_count: int
    ip_families: tuple[str, ...]
    remote_ip_digests: tuple[str, ...]


def _header_value(raw: bytes, name: str) -> str | None:
    target = name.lower() + ":"
    value = None
    for line in raw.decode("iso-8859-1", errors="replace").splitlines():
        if line.lower().startswith(target):
            value = line.split(":", 1)[1].strip()
    return value


def _proxy_scrubbed_env() -> dict[str, str]:
    blocked = {
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    }
    return {k: v for k, v in os.environ.items() if k not in blocked}


def _ip_for_resolve(ip: str) -> str:
    parsed = ipaddress.ip_address(ip)
    return f"[{parsed.compressed}]" if parsed.version == 6 else parsed.compressed


def _one_hop(
    verdict: DestinationVerdict,
    *,
    timeout_seconds: float,
    connect_timeout_seconds: int,
    max_response_bytes: int,
) -> tuple[int, str, bytes, str]:
    if timeout_seconds <= 0:
        raise TransportError("object_deadline_exhausted")

    errors: list[str] = []
    for candidate_ip in verdict.resolved_ips:
        with tempfile.TemporaryDirectory(prefix="panam-wave6-hop-") as tmp:
            root = Path(tmp)
            headers = root / "headers.txt"
            body = root / "body.bin"
            resolve = f"{verdict.host}:443:{_ip_for_resolve(candidate_ip)}"
            cmd = [
                "curl", "--disable",
                "--silent", "--show-error",
                "--proto", "=https",
                "--noproxy", "*",
                "--connect-timeout", str(connect_timeout_seconds),
                "--max-time", f"{max(0.1, timeout_seconds):.3f}",
                "--max-filesize", str(max_response_bytes),
                "--dump-header", str(headers),
                "--output", str(body),
                "--write-out", "%{http_code}\n%{size_download}\n%{remote_ip}\n",
                "--resolve", resolve,
                "--header", "Accept: text/html,application/rss+xml,application/atom+xml,application/xml;q=0.9,*/*;q=0.1",
                "--header", "Accept-Encoding: identity",
                "--user-agent", "PANAM-CI-Lab-OpenNewsCanary/1.0",
                verdict.canonical_url,
            ]
            cp = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                env=_proxy_scrubbed_env(),
                timeout=max(1.0, timeout_seconds + 1.0),
            )
            if cp.returncode != 0:
                errors.append(f"curl_exit_{cp.returncode}")
                continue

            parts = cp.stdout.splitlines()
            if len(parts) < 3:
                raise TransportSafetyError("curl_writeout_shape_invalid")
            try:
                status = int(parts[-3])
            except ValueError as exc:
                raise TransportSafetyError("curl_status_invalid") from exc
            remote_ip = parts[-1].strip()
            try:
                if ipaddress.ip_address(remote_ip) != ipaddress.ip_address(candidate_ip):
                    raise TransportSafetyError("remote_ip_not_pinned_candidate")
            except ValueError as exc:
                raise TransportSafetyError("remote_ip_invalid") from exc

            raw_headers = headers.read_bytes() if headers.exists() else b""
            raw_body = body.read_bytes() if body.exists() else b""
            if len(raw_body) > max_response_bytes:
                raise TransportSafetyError("body_exceeded_limit_after_fetch")
            content_type = _header_value(raw_headers, "content-type") or ""
            location = _header_value(raw_headers, "location") or ""
            return status, content_type, raw_body, remote_ip + "\n" + location

    raise TransportError("all_validated_addresses_failed:" + ",".join(errors))


def fetch_public_url(
    url: str,
    *,
    allowed_hosts: Iterable[str],
    max_redirects: int,
    connect_timeout_seconds: int,
    total_object_timeout_seconds: int,
    max_response_bytes: int,
) -> FetchOutcome:
    current = url
    deadline = time.monotonic() + total_object_timeout_seconds
    total_bytes = 0
    redirects = 0
    contacted_hosts: list[str] = []
    families: list[str] = []
    digests: list[str] = []

    while True:
        verdict = validate_public_https_url(current, allowed_hosts=allowed_hosts)
        remaining = deadline - time.monotonic()
        status, content_type, body, remote_and_location = _one_hop(
            verdict,
            timeout_seconds=remaining,
            connect_timeout_seconds=connect_timeout_seconds,
            max_response_bytes=max_response_bytes,
        )
        remote_ip, location = remote_and_location.split("\n", 1)
        actual_ip = ipaddress.ip_address(remote_ip)
        families.append(f"ipv{actual_ip.version}")
        digests.append(hashlib.sha256(actual_ip.compressed.encode("ascii")).hexdigest()[:16])
        contacted_hosts.append(verdict.host)
        total_bytes += len(body)

        if status in (301, 302, 303, 307, 308):
            if not location:
                raise TransportError("redirect_without_location")
            if redirects >= max_redirects:
                raise TransportError("redirect_limit_exceeded")
            next_url = urljoin(verdict.canonical_url, location)
            # Full guard runs before the next request.
            validate_public_https_url(next_url, allowed_hosts=allowed_hosts)
            current = next_url
            redirects += 1
            continue

        return FetchOutcome(
            final_url=verdict.canonical_url,
            status_code=status,
            content_type=content_type,
            body=body,
            redirect_count=redirects,
            downloaded_bytes=total_bytes,
            contacted_host_count=len(set(contacted_hosts)),
            ip_families=tuple(families),
            remote_ip_digests=tuple(digests),
        )
