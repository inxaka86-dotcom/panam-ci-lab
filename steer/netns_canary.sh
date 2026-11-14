#!/usr/bin/env bash
# PUBLIC SYNTHETIC TEST ONLY. Must run inside an unshared disposable netns/mount/pid namespace.
set -euo pipefail

fail() { printf 'STEER_NETNS_CANARY=BLOCKED reason=%s\n' "$1" >&2; exit 2; }
test "$(id -u)" = 0 || fail "not_root_in_namespace"
test -n "${PANAM_TEST_PARENT_NETNS:-}" || fail "missing_parent_namespace_identity"
test "$(readlink /proc/self/ns/net)" != "$PANAM_TEST_PARENT_NETNS" || fail "not_isolated_netns"
test -x upstream-steer/build/steer || fail "binary_missing"
for cmd in ip nft; do command -v "$cmd" >/dev/null || fail "missing_${cmd}"; done

# A fresh Linux network namespace has only loopback and no external routes.
links="$(ip -o link show | wc -l | tr -d '[:space:]')"
test "$links" = 1 || fail "unexpected_network_interfaces"
ip -o link show lo >/dev/null || fail "loopback_missing"
test -z "$(ip -4 route show default)" || fail "ipv4_default_route_present"
test -z "$(ip -6 route show default)" || fail "ipv6_default_route_present"
ip link set lo up

# Reject silent '0' skips by requiring a working real kernel nft table first.
nft add table inet steer_disposable_probe || fail "nft_kernel_unavailable"
nft list table inet steer_disposable_probe >/dev/null || fail "nft_readback_failed"
nft delete table inet steer_disposable_probe || fail "nft_cleanup_failed"
echo 'STEER_NETNS_PRECHECK=PASS isolated_namespace=true default_routes=none real_nft=true'

# Upstream self-test normally unshares a netns or skips when unavailable.
# We already proved isolation; suppress its auto-unshare, not its test body.
cd upstream-steer
export APPLYNFT_INNER=1
sh tests/applynft.sh 2>&1 | tee "${RUNNER_TEMP:-/tmp}/steer-real-nft.log"
grep -Eq '^applynft: [1-9][0-9]* passed, 0 failed$' "${RUNNER_TEMP:-/tmp}/steer-real-nft.log" || fail "no_real_success_summary"
if grep -Eiq 'пропускаю|skipped|SKIP:' "${RUNNER_TEMP:-/tmp}/steer-real-nft.log"; then
  fail "upstream_test_skipped"
fi
echo 'STEER_REAL_NFT_APPLY=PASS'
