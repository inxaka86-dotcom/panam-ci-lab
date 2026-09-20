#!/usr/bin/env python3
from destination_guard_v1 import DestinationGuardError, validate_public_https_url

ANSWERS = {
    "public.example": ("1.1.1.1",),
    "mixed.example": ("1.1.1.1", "10.0.0.1"),
    "private.example": ("192.168.1.2",),
    "empty.example": (),
}


def resolver(host: str, port: int):
    assert port == 443
    return ANSWERS.get(host, ())


def rejected(url: str, allowed: list[str], prefix: str) -> None:
    try:
        validate_public_https_url(url, allowed_hosts=allowed, resolver=resolver)
    except DestinationGuardError as exc:
        assert str(exc).startswith(prefix), (url, exc, prefix)
    else:
        raise AssertionError(f"expected rejection: {url}")


def main() -> int:
    allowed = list(ANSWERS)
    verdict = validate_public_https_url(
        "https://PUBLIC.example./x?q=1#fragment",
        allowed_hosts=allowed,
        resolver=resolver,
    )
    assert verdict.canonical_url == "https://public.example/x?q=1"
    assert verdict.resolved_ips == ("1.1.1.1",)

    rejected("http://public.example/", allowed, "scheme_not_https")
    rejected("https://u:p@public.example/", allowed, "userinfo_forbidden")
    rejected("https://127.0.0.1/", allowed, "ip_literal_forbidden")
    rejected("https://[::1]/", allowed, "ip_literal_forbidden")
    rejected("https://169.254.169.254/latest/meta-data/", allowed, "ip_literal_forbidden")
    rejected("https://localhost/", allowed, "host_not_fqdn")
    rejected("https://service.internal/", allowed, "internal_name_forbidden")
    rejected("https://public.example:8443/", allowed, "port_not_443")
    rejected("https://not-allowed.example/", allowed, "host_not_allowlisted")
    rejected("https://mixed.example/", allowed, "dns_non_global")
    rejected("https://private.example/", allowed, "dns_non_global")
    rejected("https://empty.example/", allowed, "dns_empty")

    print("PANAM_CI_LAB_DESTINATION_GUARD_V1=PASS")
    print("NETWORK_REQUESTS_EXECUTED=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
