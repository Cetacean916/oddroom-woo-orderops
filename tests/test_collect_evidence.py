#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


with tempfile.TemporaryDirectory(prefix="pf07-collector-test-") as temporary:
    project = Path(temporary) / "project"
    for directory in ("scripts", "fixtures", "evidence/raw/artifacts"):
        (project / directory).mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "scripts/collect-evidence", project / "scripts/collect-evidence")
    shutil.copy2(ROOT / "scripts/acceptance_semantics.py", project / "scripts/acceptance_semantics.py")
    (project / "fixtures/acceptance-fixtures.json").write_text(json.dumps({
        "schema_version": 1,
        "classification": "PUBLIC_ORIGINAL_SAFE_SYNTHETIC",
        "fixtures": [{
            "id": "normal-order",
            "acceptance_id": "GATE-01",
            "record": "e2e-normal-order.json",
            "probe_command": "scripts/probe-core-acceptance --fixture normal-order",
            "scenario_tags": ["synthetic"],
            "required_artifacts": ["gate01_order_variety_trace"],
            "assertions": [
                {"path": "simple_product_orders", "operator": "eq", "expected": 1},
                {"path": "variable_product_orders", "operator": "eq", "expected": 1},
                {"path": "coupon_orders", "operator": "eq", "expected": 1},
                {"path": "woocommerce_admin_and_storage_observed", "operator": "eq", "expected": True},
                {"path": "immutable_payload_hashes_valid", "operator": "eq", "expected": True},
            ],
        }],
    }, indent=2) + "\n", encoding="utf-8")
    (project / "evidence/raw/protected-artifact-inventory.json").write_text(
        '{"schema_version":1,"artifacts":{}}\n', encoding="utf-8"
    )
    (project / "fixtures/run").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (project / "fixtures/run").chmod(0o755)

    probe_source = '''#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path

def payload(order_id, email, sku):
    raw=json.dumps({"order":{"id":order_id,"customer":{"email":email},"items":[{"sku":sku,"quantity":1}]}},separators=(",",":"))
    return {"payload_json":raw,"stored_payload_hash":hashlib.sha256(raw.encode()).hexdigest()}

output=Path(os.environ["PF07_EVIDENCE_OUTPUT_DIR"])
if os.environ.get("PF07_FIXTURE_ID") != "normal-order":
    raise SystemExit("collector fixture identity was not propagated")
trace={"schema_version":1,"fixture_id":"normal-order","orders":[
    {"order_id":1,"product_id":11,"variation_id":0,"shape":"simple","coupon_applied":False,"payload":payload(1,"a@example.com","A")},
    {"order_id":2,"product_id":12,"variation_id":22,"shape":"variable","coupon_applied":False,"payload":payload(2,"b@example.com","B")},
    {"order_id":3,"product_id":13,"variation_id":0,"shape":"coupon","coupon_applied":True,"payload":payload(3,"c@example.com","C")},
],"admin_order_ids":[1,2,3],"storage_order_ids":[1,2,3]}
(output/"trace.json").write_text(json.dumps(trace)+"\\n")
print(json.dumps({"observations":{"simple_product_orders":1,"variable_product_orders":1,"coupon_orders":1,"woocommerce_admin_and_storage_observed":True,"immutable_payload_hashes_valid":True},"artifacts":{"gate01_order_variety_trace":"trace.json"}}))
'''
    probe = project / "scripts/probe-core-acceptance"
    probe.write_text(probe_source, encoding="utf-8")
    probe.chmod(0o755)
    collector = project / "scripts/collect-evidence"
    collector.chmod(0o755)
    environment = os.environ.copy()
    environment.update({
        "ODDROOM_RUN_ID": "12345678-1234-4123-8123-123456789abc",
        "PF07_SCRATCH_ROOT": temporary,
    })
    command = [
        str(collector), "--fixture", "normal-order", "--replace", "--",
        "scripts/probe-core-acceptance", "--fixture", "normal-order",
    ]
    result = subprocess.run(command, cwd=project, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(result.returncode == 0, f"valid transactional collection failed: {result.stderr}")
    record = json.loads((project / "evidence/raw/e2e-normal-order.json").read_text(encoding="utf-8"))
    require(record["command_or_probe"] == "scripts/probe-core-acceptance --fixture normal-order", "collector did not bind the exact executable command")
    artifact = project / "evidence/raw/artifacts/gate01_order_variety_trace.json"
    require(record["artifact_hashes"]["gate01_order_variety_trace"] == hashlib.sha256(artifact.read_bytes()).hexdigest(), "collector artifact commitment differs")
    manifest_lines = (project / "evidence/raw/evidence-manifest.sha256").read_text(encoding="utf-8").splitlines()
    require(any(line.endswith("evidence/raw/e2e-normal-order.json") for line in manifest_lines), "transaction manifest omitted the canonical record")

    before = snapshot(project / "evidence/raw")
    probe.write_text(probe_source.replace('"coupon_orders":1', '"coupon_orders":2'), encoding="utf-8")
    probe.chmod(0o755)
    failed = subprocess.run(command, cwd=project, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(failed.returncode != 0, "collector accepted an observation that differed from artifact-derived truth")
    require(snapshot(project / "evidence/raw") == before, "failed collection changed canonical evidence bytes")

print("PASS: evidence collection is exact-command-bound, artifact-derived, and failure-atomic")
