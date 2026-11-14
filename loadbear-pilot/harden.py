#!/usr/bin/env python3
"""Apply narrow, fail-closed LoadBear hardening to a pinned ephemeral upstream checkout.

PUBLIC RESEARCH ONLY. No PANAM configuration or deployment integration.
This is deliberately not a general-purpose patcher.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one source match, got {count}")
    return text.replace(old, new, 1)


def harden(root: pathlib.Path) -> None:
    main_path = root / "cmd/loadbear/main.go"
    proxy_path = root / "internal/proxy/proxy.go"
    main = main_path.read_text(encoding="utf-8")
    proxy = proxy_path.read_text(encoding="utf-8")

    # SIGHUP must not terminate the process or pretend to reload configuration.
    main = once(
        main,
        "signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM, syscall.SIGHUP)",
        "signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)",
        "shutdown signals",
    )
    main = once(
        main,
        "\tdefer stopSignals()\n",
        "\tdefer stopSignals()\n"
        "\tsighupSignals := make(chan os.Signal, 1)\n"
        "\tsignal.Notify(sighupSignals, syscall.SIGHUP)\n"
        "\tdefer signal.Stop(sighupSignals)\n",
        "SIGHUP channel",
    )
    start_marker = "\t\tcase <-time.After(200 * time.Millisecond):"
    end_marker = "\n\t\t}\n\t}\n}\n\nfunc signalCh()"
    if main.count(start_marker) != 1 or main.count(end_marker) != 1:
        raise RuntimeError("reload select: source shape changed")
    start = main.index(start_marker)
    end = main.index(end_marker, start)
    main = (
        main[:start]
        + '\t\tcase <-sighupSignals:\n'
        + '\t\t\tlogger.Warn("SIGHUP received; hot reload unsupported, restart required")'
        + main[end:]
    )
    start_marker = "\nfunc signalCh() chan os.Signal {"
    end_marker = "\nfunc shutdownServer("
    if main.count(start_marker) != 1 or main.count(end_marker) != 1:
        raise RuntimeError("stale reload helpers: source shape changed")
    start = main.index(start_marker)
    end = main.index(end_marker, start)
    main = main[:start] + "\n" + main[end:]

    # Forwarded-Proto may only be taken from the immediate explicitly trusted peer.
    # Untrusted or invalid client headers must be replaced with the actual scheme.
    old_proto = (
        '\tif r.Header.Get("X-Forwarded-Proto") == "" {\n'
        '\t\tr.Header.Set("X-Forwarded-Proto", schemeFromRequest(r))\n'
        '\t}'
    )
    new_proto = (
        '\toriginalProto := schemeFromRequest(r)\n'
        '\tif isTrustedProxy(r.RemoteAddr, h.config.RateLimit.TrustedProxies) {\n'
        '\t\tforwardedProto := strings.ToLower(strings.TrimSpace(r.Header.Get("X-Forwarded-Proto")))\n'
        '\t\tif forwardedProto == "http" || forwardedProto == "https" {\n'
        '\t\t\toriginalProto = forwardedProto\n'
        '\t\t}\n'
        '\t}\n'
        '\tr.Header.Set("X-Forwarded-Proto", originalProto)'
    )
    proxy = once(proxy, old_proto, new_proto, "inbound forwarded proto")
    proxy = once(
        proxy,
        'req.Out.Header.Set("X-Forwarded-Proto", schemeFromRequest(r))',
        'req.Out.Header.Set("X-Forwarded-Proto", originalProto)',
        "outbound forwarded proto",
    )

    main_path.write_text(main, encoding="utf-8")
    proxy_path.write_text(proxy, encoding="utf-8")
    subprocess.run(["gofmt", "-w", str(main_path), str(proxy_path)], check=True)
    print("LOADBEAR_EPHEMERAL_PATCH=APPLIED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream_checkout", type=pathlib.Path)
    harden(parser.parse_args().upstream_checkout.resolve())
