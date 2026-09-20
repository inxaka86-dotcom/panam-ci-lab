from __future__ import annotations

import json
import os
import resource
import socket
import sys
import time
from pathlib import Path

UPSTREAM_SHA_EXPECTED = "ebb0e9b4deb0bf8fa8983e6324276a51f091ab43"


def cyrillic_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    cyr = [ch for ch in letters if "\u0400" <= ch <= "\u052f"]
    return len(cyr) / len(letters)


class NetworkGuard:
    def __init__(self) -> None:
        self.attempts: list[str] = []
        self._orig_connect = socket.socket.connect
        self._orig_connect_ex = socket.socket.connect_ex
        self._orig_create_connection = socket.create_connection

    def _blocked(self, *args, **kwargs):
        target = repr(args[0] if args else kwargs)
        self.attempts.append(target)
        raise RuntimeError(f"network disabled during measured benchmark: {target}")

    def __enter__(self):
        socket.socket.connect = self._blocked
        socket.socket.connect_ex = self._blocked
        socket.create_connection = self._blocked
        return self

    def __exit__(self, exc_type, exc, tb):
        socket.socket.connect = self._orig_connect
        socket.socket.connect_ex = self._orig_connect_ex
        socket.create_connection = self._orig_create_connection


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: open_news_offline_benchmark.py <upstream-root> <upstream-sha>", file=sys.stderr)
        return 2

    upstream_root = Path(sys.argv[1]).resolve()
    upstream_sha = sys.argv[2].strip()
    if upstream_sha != UPSTREAM_SHA_EXPECTED:
        raise SystemExit(f"unexpected upstream SHA: {upstream_sha}")
    if not (upstream_root / "open_news").is_dir():
        raise SystemExit("upstream open_news package directory missing")

    sys.path.insert(0, str(upstream_root))

    import open_news
    from open_news.core.extractor import extract_article
    from open_news.feeds.sources import from_rss
    from open_news.processing.dedupe import dedupe_articles, normalize_url
    from open_news.processing.domain_filter import filter_by_domain
    from open_news.processing.language_guard import filter_by_language
    from open_news.processing.ranker import sort_articles
    from open_news.processing.token_filter import filter_articles, matches_query

    loaded_from = Path(open_news.__file__).resolve()
    if upstream_root not in loaded_from.parents:
        raise SystemExit(f"open_news loaded outside pinned source tree: {loaded_from}")

    fixture_dir = Path(__file__).resolve().parent / "fixtures"
    html = (fixture_dir / "article_ru.html").read_text(encoding="utf-8")
    rss_bytes = (fixture_dir / "rss_ru.xml").read_bytes()

    cases: list[dict] = []

    def check(case_id: str, condition: bool, **details) -> None:
        cases.append({"id": case_id, "pass": bool(condition), "details": details})

    started = time.perf_counter()
    with NetworkGuard() as guard:
        extracted = extract_article(html, "https://example.ru/legal/digital-platforms")
        expected_title = "Синтетическая новость о цифровом регулировании"
        check("extract_title_exact", extracted.get("title") == expected_title, observed=extracted.get("title"))
        check("extract_language_ru", extracted.get("meta", {}).get("language") == "ru", observed=extracted.get("meta", {}).get("language"))
        body = extracted.get("text") or ""
        check("extract_body_length", len(body) >= 500, length=len(body))
        ratio = cyrillic_ratio(body)
        check("extract_cyrillic_preservation", ratio >= 0.85, cyrillic_ratio=round(ratio, 4))
        check("extract_publish_date", str(extracted.get("publish_date", "")).startswith("2026-09-18T10:30:00"), observed=extracted.get("publish_date"))

        rss_articles = from_rss(rss_bytes, limit=10, resolve_google_urls=False)
        check("rss_local_count", len(rss_articles) == 2, observed=len(rss_articles))
        check("rss_cyrillic_title", bool(rss_articles) and "Изменения" in rss_articles[0].get("title", ""), observed=(rss_articles[0].get("title") if rss_articles else None))

        exact_input = [
            {"title": "Одинаковая тестовая новость", "url": "https://www.example.ru/news/42?utm_source=a", "source": "Example"},
            {"title": "Одинаковая тестовая новость", "url": "https://example.ru/news/42?utm_campaign=b", "source": "Example"},
            {"title": "Другая тестовая новость", "url": "https://example.ru/news/43", "source": "Example"},
        ]
        exact_out = dedupe_articles([dict(x) for x in exact_input], fuzzy=False)
        check("dedupe_exact_url", len(exact_out) == 2, observed=len(exact_out))
        norm_a = normalize_url(exact_input[0]["url"])
        norm_b = normalize_url(exact_input[1]["url"])
        check("normalize_tracking_params", norm_a == norm_b, normalized_a=norm_a, normalized_b=norm_b)

        fuzzy_input = [
            {"title": "Новый порядок регистрации товарных знаков", "url": "https://a.example/1"},
            {"title": "Новый порядок регистрации товарных знаков", "url": "https://b.example/2"},
            {"title": "Изменения в правилах цифровых платформ", "url": "https://c.example/3"},
        ]
        fuzzy_out = dedupe_articles([dict(x) for x in fuzzy_input], fuzzy=True)
        check("dedupe_fuzzy_russian", len(fuzzy_out) == 2, observed=len(fuzzy_out))

        query_article = {
            "title": "Изменения в правилах цифровых платформ",
            "description": "Новый порядок применяется к операторам платформ.",
            "text": "Подробный синтетический текст.",
            "url": "https://example.ru/news/44",
        }
        check("unicode_query_exact_phrase", matches_query(query_article, "цифровых платформ", "exact_phrase", ["title", "description"]))
        filtered = filter_articles([query_article], query="изменения платформ", query_mode="all", search_in=["title", "description"])
        check("unicode_query_all_terms", len(filtered) == 1, observed=len(filtered))

        language_input = [
            {
                "title": "Регулятор опубликовал подробные разъяснения для участников рынка",
                "description": "Синтетический русскоязычный текст для устойчивого определения языка.",
            },
            {
                "title": "Regulator published detailed guidance for market participants",
                "description": "Synthetic English text intended only for deterministic language filtering.",
            },
        ]
        ru_only = filter_by_language(language_input, "ru")
        check("language_filter_russian", len(ru_only) == 1 and "Регулятор" in ru_only[0]["title"], observed_titles=[x["title"] for x in ru_only])

        domains = filter_by_domain(
            [{"url": "https://law.example.ru/a"}, {"url": "https://other.example/b"}],
            whitelist=["example.ru"],
        )
        check("domain_subdomain_whitelist", len(domains) == 1, observed=len(domains))

        ordered = sort_articles(
            [
                {"title": "старее", "published": "2026-09-17T10:00:00+03:00"},
                {"title": "новее", "published": "2026-09-18T10:00:00+03:00"},
            ],
            sort_by="date",
        )
        check("date_sort_descending", [x["title"] for x in ordered] == ["новее", "старее"], observed=[x["title"] for x in ordered])

    elapsed = time.perf_counter() - started
    peak_rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    passed = sum(1 for c in cases if c["pass"])
    result = {
        "schema": "panam-ci-lab.open-news-offline-benchmark.v1",
        "upstream_repository": "alphap365/open-news",
        "upstream_sha": upstream_sha,
        "python": sys.version.split()[0],
        "loaded_from": str(loaded_from),
        "network_guard": {
            "mode": "python_socket_fail_closed",
            "attempt_count": len(guard.attempts),
            "attempts": guard.attempts,
        },
        "metrics": {
            "cases_passed": passed,
            "cases_total": len(cases),
            "pass_rate": round(passed / len(cases), 4) if cases else 0.0,
            "elapsed_seconds": round(elapsed, 6),
            "peak_rss_kib": peak_rss_kib,
            "extracted_body_chars": len(body),
            "extracted_body_cyrillic_ratio": round(ratio, 4),
        },
        "cases": cases,
        "production_authority": False,
        "private_data_used": False,
        "network_during_measured_run_authorized": False,
    }

    out_path = Path(os.environ.get("OPEN_NEWS_BENCHMARK_OUTPUT", "wave5-result.json"))
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if guard.attempts:
        print("BENCHMARK_NETWORK_GUARD=FAIL")
        return 1
    if passed != len(cases):
        print(f"BENCHMARK_CASES=FAIL {passed}/{len(cases)}")
        return 1

    print(f"BENCHMARK_CASES=PASS {passed}/{len(cases)}")
    print("BENCHMARK_NETWORK_GUARD=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
