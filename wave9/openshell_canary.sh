#!/usr/bin/env bash
set -euo pipefail

sandbox_name="${1:-wave9-openshell}"
policy_path="${2:-wave9/openshell_github_readonly.yaml}"
result_path="${3:-${RUNNER_TEMP:-/tmp}/wave9-openshell-result.json}"
effective_policy_path="${4:-${RUNNER_TEMP:-/tmp}/wave9-openshell-effective-policy.yaml}"
image_name="${5:-wave9-openshell-canary:local}"

cleanup() {
  openshell sandbox delete "${sandbox_name}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

openshell status
openshell sandbox create \
  --name "${sandbox_name}" \
  --from "${image_name}" \
  --policy "${policy_path}" \
  --no-auto-providers \
  --detach

# Capture what the sandbox is actually enforcing.
openshell policy get "${sandbox_name}" --full > "${effective_policy_path}"

# Positive control: the only intended egress succeeds.
get_output="$(
  openshell sandbox exec -n "${sandbox_name}" --no-login-shell -- \
    curl -fsS --max-time 15 https://api.github.com/zen
)"
test -n "${get_output}"

# L7 negative controls: every mutating REST method must be denied.
for method in POST PUT PATCH DELETE; do
  openshell sandbox exec -n "${sandbox_name}" --no-login-shell -- \
    sh -c '
      set -eu
      method="$1"
      body="/tmp/wave9-${method}.body"
      code="$(curl -sS --max-time 15 -o "${body}" -w "%{http_code}" -X "${method}" \
        -H "Content-Type: application/json" \
        -d "{"title":"wave9-denied"}" \
        https://api.github.com/repos/octocat/hello-world/issues)"
      test "${code}" = "403"
      grep -q "policy_denied" "${body}"
    ' sh "${method}"
done

# Host allowlist negative control.
if openshell sandbox exec -n "${sandbox_name}" --no-login-shell -- \
  curl -fsS --max-time 15 https://example.com/ >/dev/null 2>&1; then
  echo "unexpected unrelated-host success" >&2
  exit 1
fi

# Binary binding negative control: Python must not inherit curl's network grant.
if openshell sandbox exec -n "${sandbox_name}" --no-login-shell -- \
  python3 -c 'import urllib.request; urllib.request.urlopen("https://api.github.com/zen", timeout=10).read()' \
  >/dev/null 2>&1; then
  echo "unexpected alternate-binary network success" >&2
  exit 1
fi

# Filesystem negative control.
if openshell sandbox exec -n "${sandbox_name}" --no-login-shell -- \
  touch /etc/wave9-openshell-write-test >/dev/null 2>&1; then
  echo "unexpected /etc write success" >&2
  exit 1
fi

# No credential/provider material may be present in this provider-free sandbox.
openshell sandbox exec -n "${sandbox_name}" --no-login-shell -- \
  sh -c '
    if env | grep -E "^(GITHUB_TOKEN|GH_TOKEN|OPENAI_API_KEY|ANTHROPIC_API_KEY|NVIDIA_API_KEY)="; then
      echo "unexpected credential environment" >&2
      exit 1
    fi
  '

openshell_version="$(openshell --version | tr -d "\r")"

python3 - "${result_path}" "${openshell_version}" <<'PY'
import json
import sys

path, version = sys.argv[1:3]
result = {
    "schema": "panam-ci-lab.wave9.openshell-public-canary.v1",
    "openshell_version": version,
    "github_get_allowed": True,
    "github_mutating_methods_denied": ["POST", "PUT", "PATCH", "DELETE"],
    "unrelated_host_denied": True,
    "alternate_binary_denied": True,
    "etc_write_denied": True,
    "credential_environment_absent": True,
    "provider_attached": False,
    "private_repository_access": False,
    "production_authority": False,
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(result, fh, sort_keys=True, separators=(",", ":"))
    fh.write("\n")
print(json.dumps(result, sort_keys=True))
PY

# Teardown is part of the acceptance contract, not merely best effort.
openshell sandbox delete "${sandbox_name}"
trap - EXIT

if openshell sandbox list | grep -Fq "${sandbox_name}"; then
  echo "sandbox still present after delete" >&2
  exit 1
fi
