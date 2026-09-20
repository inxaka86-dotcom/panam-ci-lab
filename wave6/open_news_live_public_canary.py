#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
from urllib.parse import urlsplit

from guarded_fetch_v1 import TransportError, TransportSafetyError, fetch_public_url
from destination_guard_v1 import DestinationGuardError


UPSTREAM_SHA = "ebb0e9b4deb0bf8fa8983e6324276a51f091ab43"


def cyrillic_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    cyr = [ch for ch in letters if "\u0400" <= ch <= "\u052f"]
    return len(cyr) / len(letters)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: live_canary.py <upstream-root> <sources-json>", file=sys.stderr)
        return 2

    upstream_root = Path(sys.argv[1]).resolve()
    plan_path = Path(sys.argv[2]).resolve()
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)

    if plan.get("upstream_sha") != UPSTREAM_SHA:
        raise SystemExit("upstream_sha_mismatch")
    sources = plan["sources"]
    limits = plan["limits"]
    if len(sources) > limits["max_sources"]:
        raise SystemExit("source_count_limit_exceeded")
    if len(sources) > limits["max_objects"]:
        raise SystemExit("object_count_limit_exceeded")

    allowed_hosts = sorted({urlsplit(item["url"]).hostname for item in sources})
    if None in allowed_hosts:
        raise SystemExit("source_host_missing")

    sys.path.insert(0, str(upstream_root))
    import open_news
    from open_news.core.extractor import extract_article
    from open_news.feeds.sources import from_rss
    from open_news.processing.dedupe import dedupe_articles

    loaded_from = Path(open_news.__file__).resolve()
    if upstream_root not in loaded_from.parents:
        raise SystemExit("open_news_not_loaded_from_pinned_source")

    started = time.perf_counter()
    source_results = []
    aggregate_bytes = 0
    safety_failures = 0
    transport_failures = 0
    html_extract_success = 0
    rss_parse_success = 0
    fetch_2xx = 0

    for item in sources:
        record = {
            "id": item["id"],
            "kind": item["kind"],
            "host": urlsplit(item["url"]).hostname,
            "url_sha256": sha256(item["url"].encode("utf-8")),
        }
        try:
            outcome = fetch_public_url(
                item["url"],
                allowed_hosts=allowed_hosts,
                max_redirects=limits["max_redirects_per_object"],
                connect_timeout_seconds=limits["connect_timeout_seconds"],
                total_object_timeout_seconds=limits["total_object_timeout_seconds"],
                max_response_bytes=limits["max_response_bytes"],
            )
            aggregate_bytes += outcome.downloaded_bytes
            if aggregate_bytes > limits["max_aggregate_bytes"]:
                raise TransportSafetyError("aggregate_download_limit_exceeded")

            record.update({
                "fetch": "ok",
                "http_status": outcome.status_code,
                "content_type": outcome.content_type.split(";", 1)[0].strip().lower(),
                "body_bytes": len(outcome.body),
                "body_sha256": sha256(outcome.body),
                "redirect_count": outcome.redirect_count,
                "contacted_host_count": outcome.contacted_host_count,
                "ip_families": list(outcome.ip_families),
                "remote_ip_digests": list(outcome.remote_ip_digests),
                "final_url_sha256": sha256(outcome.final_url.encode("utf-8")),
            })
            if 200 <= outcome.status_code < 300:
                fetch_2xx += 1

            if item["kind"] == "rss":
                parsed = from_rss(outcome.body, limit=10, resolve_google_urls=False)
                deduped = dedupe_articles([dict(x) for x in parsed], fuzzy=True)
                titles = " ".join(str(x.get("title") or "") for x in parsed)
                record["processing"] = {
                    "mode": "rss",
                    "item_count": len(parsed),
                    "deduped_count": len(deduped),
                    "title_cyrillic_ratio": round(cyrillic_ratio(titles), 4),
                }
                if len(parsed) > 0:
                    rss_parse_success += 1
            elif item["kind"] == "html":
                text = outcome.body.decode("utf-8", errors="replace")
                extracted = extract_article(text, outcome.final_url)
                body = extracted.get("text") or ""
                title = extracted.get("title") or ""
                record["processing"] = {
                    "mode": "html",
                    "title_chars": len(title),
                    "title_sha256": sha256(title.encode("utf-8")) if title else None,
                    "text_chars": len(body),
                    "text_sha256": sha256(body.encode("utf-8")) if body else None,
                    "text_cyrillic_ratio": round(cyrillic_ratio(body), 4),
                    "has_publish_date": bool(extracted.get("publish_date")),
                    "language": (extracted.get("meta") or {}).get("language"),
                }
                if len(body) >= 150 or len(title) >= 20:
                    html_extract_success += 1
            else:
                raise TransportSafetyError("unknown_source_kind")

        except (DestinationGuardError, TransportSafetyError) as exc:
            safety_failures += 1
            record.update({"fetch": "safety_fail", "error": str(exc)})
        except TransportError as exc:
            transport_failures += 1
            record.update({"fetch": "transport_fail", "error": str(exc)})
        except Exception as exc:
            transport_failures += 1
            record.update({"fetch": "processing_fail", "error_type": type(exc).__name__})

        source_results.append(record)

    elapsed = time.perf_counter() - started
    peak_rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    functional = "FAIL"
    if (
        safety_failures == 0
        and fetch_2xx >= 3
        and html_extract_success >= 2
        and rss_parse_success >= 1
    ):
        functional = "PASS"
    elif safety_failures == 0 and fetch_2xx >= 1:
        functional = "PARTIAL"

    result = {
        "schema": "panam-ci-lab.open-news-live-public-canary-result.v1",
        "classification": "LIVE_PUBLIC_RESEARCH_EVIDENCE",
        "upstream_repository": "alphap365/open-news",
        "upstream_sha": UPSTREAM_SHA,
        "source_plan_sha256": sha256(plan_bytes),
        "allowed_hosts": allowed_hosts,
        "metrics": {
            "sources_total": len(sources),
            "fetch_2xx": fetch_2xx,
            "html_extract_success": html_extract_success,
            "rss_parse_success": rss_parse_success,
            "safety_failures": safety_failures,
            "transport_or_processing_failures": transport_failures,
            "aggregate_downloaded_bytes": aggregate_bytes,
            "elapsed_seconds": round(elapsed, 6),
            "peak_rss_kib": peak_rss_kib,
        },
        "functional_result": functional,
        "sources": source_results,
        "security": {
            "address_pinning": "curl_resolve_validated_ip",
            "tls_hostname_verification": True,
            "automatic_redirects": False,
            "ambient_proxy": false,
            "credentials_used": false,
            "private_data_used": false,
            "production_authority": false,
        },
    }

    out = Path(os.environ.get("OPEN_NEWS_LIVE_RESULT", "wave6-result.json"))
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"WAVE6_SAFETY_FAILURES={safety_failures}")
    print(f"WAVE6_FUNCTIONAL_RESULT={functional}")

    if safety_failures:
        return 1
    if functional == "FAIL":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
