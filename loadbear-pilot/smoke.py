#!/usr/bin/env python3
"""Loopback-only synthetic integration test for a LoadBear research binary."""
from __future__ import annotations

import argparse
import collections
import json
import os
import signal
import subprocess
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def make_backend(name: str):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            content = (
                b"healthy"
                if self.path == "/health"
                else f"{name}|{self.headers.get('X-Forwarded-Proto', '')}".encode()
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return server, worker


def port():
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    p = sock.getsockname()[1]
    sock.close()
    return p


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def read(url: str, headers: dict[str, str] | None = None) -> str:
    req = urllib.request.Request(url, headers=headers or {})
    with OPENER.open(req, timeout=2) as res:
        if res.status != 200:
            raise AssertionError(f"HTTP {res.status} for {url}")
        return res.read().decode("utf-8")


def until(predicate, label: str, timeout: float = 10):
    deadline = time.monotonic() + timeout
    error = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception as exc:
            error = exc
        time.sleep(0.12)
    raise AssertionError(f"TIMEOUT: {label}; last error={error}")


def config_text(listen: int, admin: int, backends: list[int], trusted: bool):
    backend_yaml = "\n".join(
        f'  - url: "http://127.0.0.1:{p}"\n    weight: 1'
        for p in backends
    )
    trusted_yaml = '["127.0.0.1/32"]' if trusted else "[]"
    return f"""
listen: "127.0.0.1:{listen}"
admin_listen: "127.0.0.1:{admin}"
strategy: "round_robin"
log_level: "warn"
log_format: "json"
backends:
{backend_yaml}
health:
  path: "/health"
  interval: "250ms"
  timeout: "100ms"
  healthy_threshold: 1
  unhealthy_threshold: 1
proxy:
  max_idle_conns: 20
  max_idle_conns_per_host: 10
  idle_conn_timeout: "30s"
  response_header_timeout: "2s"
  tls_handshake_timeout: "2s"
  dial_timeout: "500ms"
  request_timeout: "4s"
  retry_max_attempts: 2
  retry_backoff: "10ms"
  circuit_failure_threshold: 3
  circuit_cooldown: "1s"
rate_limit:
  enabled: false
  rate: 100
  burst: 200
  window: "1m"
  trusted_proxies: {trusted_yaml}
shutdown:
  grace_period: "2s"
"""


def start_proxy(binary: str, config: Path):
    environment = os.environ.copy()
    for key in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
        "LOADBEAR_LISTEN", "LOADBEAR_LOG_LEVEL",
    ):
        environment.pop(key, None)
    return subprocess.Popen(
        [binary, "--config", str(config), "--no-banner"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        start_new_session=True,
    )


def stop_proxy(proc):
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def run(binary: str):
    services = [make_backend(f"backend-{i}") for i in range(1, 4)]
    main_proc = None
    secondary_proc = None
    stopped = set()
    try:
        backend_ports = [server.server_address[1] for server, _ in services]
        with tempfile.TemporaryDirectory(prefix="loadbear-synthetic-") as tmp:
            tmp = Path(tmp)
            main_port, admin_port = port(), port()
            cfg = tmp / "trusted.yaml"
            cfg.write_text(config_text(main_port, admin_port, backend_ports, True), encoding="utf-8")
            main_proc = start_proxy(binary, cfg)
            api = f"http://127.0.0.1:{main_port}"
            admin = f"http://127.0.0.1:{admin_port}"
            def all_healthy():
                rows = json.loads(read(admin + "/status"))["backends"]
                return len(rows) == 3 and all(x["healthy"] for x in rows)
            until(all_healthy, "three healthy synthetic backends")
            initial = [read(api + "/work").split("|")[0] for _ in range(15)]
            totals = collections.Counter(initial)
            if set(totals) != {"backend-1", "backend-2", "backend-3"}:
                raise AssertionError(f"not all backends selected: {dict(totals)}")
            if not read(admin + "/metrics").strip():
                raise AssertionError("empty metrics")
            proto = read(api + "/work", {"X-Forwarded-Proto": "https"}).split("|")[1]
            if proto != "https":
                raise AssertionError(f"trusted HTTPS proto not preserved: {proto}")
            invalid = read(api + "/work", {"X-Forwarded-Proto": "ftp"}).split("|")[1]
            if invalid != "http":
                raise AssertionError(f"invalid proto not sanitized: {invalid}")
            main_proc.send_signal(signal.SIGHUP)
            time.sleep(0.3)
            if main_proc.poll() is not None:
                raise AssertionError("SIGHUP terminated the research proxy")
            read(api + "/work")

            server, worker = services[0]
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
            stopped.add(0)
            def first_unhealthy():
                rows = json.loads(read(admin + "/status"))["backends"]
                return bool(rows) and rows[0]["healthy"] is False
            until(first_unhealthy, "failed backend marked unhealthy")
            after = [read(api + "/work").split("|")[0] for _ in range(12)]
            if "backend-1" in after or set(after) != {"backend-2", "backend-3"}:
                raise AssertionError(f"failover result: {after}")
            stop_proxy(main_proc)
            main_proc = None

            # Spoofed forwarding must be rejected with no trusted proxies.
            public_port, public_admin = port(), port()
            untrusted_cfg = tmp / "untrusted.yaml"
            untrusted_cfg.write_text(
                config_text(public_port, public_admin, backend_ports[1:], False),
                encoding="utf-8",
            )
            secondary_proc = start_proxy(binary, untrusted_cfg)
            untrusted_url = f"http://127.0.0.1:{public_port}"
            until(lambda: read(untrusted_url + "/work"), "untrusted proxy startup")
            spoofed = read(
                untrusted_url + "/work", {"X-Forwarded-Proto": "https"}
            ).split("|")[1]
            if spoofed != "http":
                raise AssertionError(f"untrusted spoofed proto accepted: {spoofed}")
            print(
                "LOADBEAR_SMOKE=PASS "
                "backends=3 round_robin=PASS failover=PASS "
                "metrics=PASS trusted_proto=PASS untrusted_proto=PASS "
                "sighup_nonfatal=PASS localhost_only=YES"
            )
    finally:
        if main_proc:
            stop_proxy(main_proc)
        if secondary_proc:
            stop_proxy(secondary_proc)
        for i, (server, worker) in enumerate(services):
            if i not in stopped:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("binary")
    run(parser.parse_args().binary)
