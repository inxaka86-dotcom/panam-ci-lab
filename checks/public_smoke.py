from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

PAYLOAD = b"PANAM_PUBLIC_CI_LAB_V1"
ROOT = Path(__file__).resolve().parents[1]

report = {
    "schema": "panam.public-ci-lab.smoke.v1",
    "data_class": "PUBLIC_SYNTHETIC",
    "payload_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
    "private_repository_access": False,
    "production_access": False,
    "secret_required": False,
}

assert report["data_class"] == "PUBLIC_SYNTHETIC"
assert report["private_repository_access"] is False
assert report["production_access"] is False
assert report["secret_required"] is False

wave4 = ROOT / "wave4" / "production-activation" / "selftest_activation_contract_v1.py"
if wave4.exists():
    subprocess.run(["python3", str(wave4)], cwd=ROOT, check=True)

print(json.dumps(report, sort_keys=True))
print("PANAM_PUBLIC_CI_LAB_V1=PASS")
