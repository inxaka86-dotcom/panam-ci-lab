#!/usr/bin/env bash
set -euo pipefail

sandbox_name="${1:-wave10-od3b}"
policy_path="${2:-wave10/openshell_od3b.yaml}"
image_name="${3:-wave10-od3b:local}"
result_path="${4:-${RUNNER_TEMP:-/tmp}/wave10-od3b-result.json}"
probe_path="${5:-${RUNNER_TEMP:-/tmp}/wave10-od3b-post-stop.json}"
effective_policy_path="${6:-${RUNNER_TEMP:-/tmp}/wave10-od3b-effective-policy.yaml}"
log_path="${7:-${RUNNER_TEMP:-/tmp}/wave10-od3b-openshell.log}"
error_path="${8:-${RUNNER_TEMP:-/tmp}/wave10-od3b-browser.stderr.log}"

cleanup() {
  openshell sandbox delete "${sandbox_name}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

openshell sandbox create   --name "${sandbox_name}"   --from "${image_name}"   --policy "${policy_path}"   --no-auto-providers   --detach   --no-tty   -- /usr/bin/sleep 300

openshell policy get "${sandbox_name}" --full > "${effective_policy_path}"


if ! openshell sandbox exec -n "${sandbox_name}" --no-login-shell --   /opt/od3b/node /opt/od3b/live_canary.mjs > "${result_path}" 2> "${error_path}"; then
  openshell logs "${sandbox_name}" --since 5m --source sandbox > "${log_path}" 2>&1 || true
  cat "${error_path}" >&2 || true
  cat "${log_path}" >&2 || true
  exit 1
fi

openshell sandbox exec -n "${sandbox_name}" --no-login-shell --   /opt/od3b/node /opt/od3b/post_stop_probe.mjs > "${probe_path}"

openshell logs "${sandbox_name}" --since 5m --source sandbox > "${log_path}"
test -s "${log_path}"

python3 - "${result_path}" "${probe_path}" <<'PY'
import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
probe = json.load(open(sys.argv[2], encoding="utf-8"))

required_true = [
    "browser_navigation_succeeded",
    "unlisted_origin_denied",
    "ephemeral_file_written",
    "screenshot_written",
    "post_stop_action_denied",
    "workspace_reset",
    "browser_closed",
]
for key in required_true:
    assert result.get(key) is True, (key, result)

assert result.get("shell_capability") is False
assert result.get("credentials_available") is False
assert result.get("production_mounts_available") is False
assert result.get("concurrency") == 1
assert result.get("control_plane_invoked") is False
assert result.get("memory_written") is False
assert result.get("merge_performed") is False
assert result.get("deploy_performed") is False
assert probe == {
    "schema": "panam-ci-lab.wave10.od3b-post-stop-probe.v1",
    "workspace_absent": True,
    "browser_processes_absent": True,
}
PY

openshell sandbox delete "${sandbox_name}"
trap - EXIT

if openshell sandbox list | grep -Fq "${sandbox_name}"; then
  echo "sandbox still present after delete" >&2
  exit 1
fi
