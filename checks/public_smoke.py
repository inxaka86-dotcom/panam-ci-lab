from __future__ import annotations

import hashlib
import json

PAYLOAD = b"PANAM_PUBLIC_CI_LAB_V1"

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

print(json.dumps(report, sort_keys=True))
print("PANAM_PUBLIC_CI_LAB_V1=PASS")
