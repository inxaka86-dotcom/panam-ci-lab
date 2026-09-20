#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
import socket
from typing import Callable, Iterable, Sequence
from urllib.parse import urlsplit, urlunsplit


class DestinationGuardError(ValueError):
    pass


@dataclass(frozen=True)
class DestinationVerdict:
    canonical_url: str
    host: str
    port: int
    resolved_ips: tuple[str, ...]


Resolver = Callable[[str, int], Sequence[str]]
_HOST_LABEL = re.compile(r"^[A-Za-z0-9-]{1,63}$")
_BLOCKED_NAME_SUFFIXES = (
    "localhost",
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home.arpa",
)


def normalize_host(raw: str) -> str:
    host = (raw or "").strip().rstrip(".").lower()
    if not host:
        raise DestinationGuardError("host_missing")
    if any(ch.isspace() or ord(ch) < 32 for ch in host):
        raise DestinationGuardError("host_invalid_whitespace")
    if any(ch in host for ch in ("%", "\\", "/")):
        raise DestinationGuardError("host_ambiguous_encoding")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise DestinationGuardError("host_idna_invalid") from exc
        if len(host) > 253 or "." not in host:
            raise DestinationGuardError("host_not_fqdn")
        labels = host.split(".")
        if any(
            not _HOST_LABEL.fullmatch(label)
            or label.startswith("-")
            or label.endswith("-")
            for label in labels
        ):
            raise DestinationGuardError("host_label_invalid")
    return host


def default_resolver(host: str, port: int) -> tuple[str, ...]:
    found: list[str] = []
    for _family, _socktype, _proto, _canonname, sockaddr in socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    ):
        address = sockaddr[0]
        if address not in found:
            found.append(address)
    return tuple(found)


def validate_public_https_url(
    url: str,
    *,
    allowed_hosts: Iterable[str],
    resolver: Resolver | None = None,
) -> DestinationVerdict:
    try:
        parts = urlsplit(url)
        explicit_port = parts.port
    except ValueError as exc:
        raise DestinationGuardError("url_parse_failed") from exc

    if parts.scheme.lower() != "https":
        raise DestinationGuardError("scheme_not_https")
    if parts.username is not None or parts.password is not None:
        raise DestinationGuardError("userinfo_forbidden")
    if parts.hostname is None:
        raise DestinationGuardError("host_missing")

    host = normalize_host(parts.hostname)
    if host == "localhost" or host.endswith(_BLOCKED_NAME_SUFFIXES):
        raise DestinationGuardError("internal_name_forbidden")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise DestinationGuardError("ip_literal_forbidden")

    normalized_allowed = {normalize_host(item) for item in allowed_hosts}
    if host not in normalized_allowed:
        raise DestinationGuardError("host_not_allowlisted")

    port = 443 if explicit_port is None else explicit_port
    if port != 443:
        raise DestinationGuardError("port_not_443")

    resolve = resolver or default_resolver
    answers = tuple(dict.fromkeys(resolve(host, port)))
    if not answers:
        raise DestinationGuardError("dns_empty")

    global_ips: list[str] = []
    for raw in answers:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise DestinationGuardError("dns_non_ip_answer") from exc
        if not address.is_global:
            raise DestinationGuardError("dns_non_global")
        global_ips.append(address.compressed)

    canonical_url = urlunsplit(("https", host, parts.path or "/", parts.query, ""))
    return DestinationVerdict(
        canonical_url=canonical_url,
        host=host,
        port=port,
        resolved_ips=tuple(sorted(set(global_ips))),
    )
