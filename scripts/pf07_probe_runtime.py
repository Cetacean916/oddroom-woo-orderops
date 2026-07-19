from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import uuid


class ProbeRuntimeError(RuntimeError):
    pass


def _redact(message: str) -> str:
    message = re.sub(r"https?://\S+", "<url>", message)
    message = re.sub(
        r"(?i)((?:authorization|password|secret|token)\s*[=:]\s*)\S+",
        r"\1<redacted>",
        message,
    )
    return message[:300]


def run(
    command: list[str],
    *,
    label: str,
    environment: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout: int = 360,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        env=environment,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
        detail = _redact(lines[-1] if lines else "no diagnostic")
        raise ProbeRuntimeError(f"{label} failed with exit code {result.returncode}: {detail}")
    return result


def parse_json_output(result: subprocess.CompletedProcess[str], label: str) -> object:
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError as error:
        raise ProbeRuntimeError(f"{label} did not return one JSON value: {error.msg}") from error


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key) is None:
            raise ProbeRuntimeError("runtime environment contains an invalid key")
        if value.startswith(("'", '"')) and value.endswith(value[0]):
            value = value[1:-1]
        values[key] = value
    return values


NODE_EXECUTION_SANITIZER = r"""
const fs = require('fs');
const crypto = require('crypto');
const { parse } = require('/usr/local/lib/node_modules/n8n/node_modules/.pnpm/flatted@3.4.2/node_modules/flatted');
const [inputPath] = process.argv.slice(1);
const records = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
const digest = value => crypto.createHash('sha256').update(value, 'utf8').digest('hex');
const jsonItems = runs => (runs || []).flatMap(run => (run?.data?.main || []).flatMap(branch => (branch || []).map(item => item?.json).filter(Boolean)));
const findEnvelope = (value, seen = new Set(), depth = 0) => {
  if (!value || typeof value !== 'object' || depth > 10 || seen.has(value)) return null;
  seen.add(value);
  if (typeof value.event_key === 'string' && typeof value.result === 'string' && typeof value.processing_phase === 'string') return value;
  for (const child of Object.values(value)) {
    const found = findEnvelope(child, seen, depth + 1);
    if (found) return found;
  }
  return null;
};
const output = [];
for (const record of records) {
  const decoded = parse(record.data);
  const runData = decoded?.resultData?.runData || {};
  const webhookItems = (runData['Signed Raw Webhook'] || []).flatMap(run => (run?.data?.main || []).flatMap(branch => branch || []));
  const rawBase64 = webhookItems.map(item => item?.binary?.data?.data).find(value => typeof value === 'string') || null;
  const verified = jsonItems(runData['Verify HMAC Then Decode']);
  const verifiedItem = verified.find(item => item?.authorized === true) || verified[0] || null;
  const eventKey = typeof verifiedItem?.event_key === 'string' ? verifiedItem.event_key : null;
  let envelope = null;
  for (const runs of Object.values(runData)) {
    for (const item of jsonItems(runs)) envelope = findEnvelope(item) || envelope;
  }
  const nodeNames = Object.keys(runData);
  output.push({
    execution_id: Number(record.id),
    status: record.status,
    started_at: record.startedAt,
    stopped_at: record.stoppedAt,
    event_key_sha256: eventKey ? digest(eventKey) : null,
    verified_authorized: verifiedItem?.authorized === true,
    ingress_raw_body_sha256: rawBase64 ? crypto.createHash('sha256').update(Buffer.from(rawBase64, 'base64')).digest('hex') : null,
    verified_payload_sha256: verifiedItem?.payload ? digest(JSON.stringify(verifiedItem.payload)) : null,
    executed_nodes: nodeNames,
    hubspot_outbound_call_count: nodeNames.filter(name => name.startsWith('HubSpot 2026-03 ')).reduce((sum, name) => sum + (runData[name] || []).length, 0),
    association_outbound_call_count: ['HubSpot 2026-03 Default Association','HubSpot 2026-03 Association Read'].reduce((sum, name) => sum + (runData[name] || []).length, 0),
    slack_outbound_call_count: (runData['Slack chat.postMessage'] || []).length,
    envelope: envelope ? {
      result: envelope.result,
      processing_phase: envelope.processing_phase,
      slack_status: envelope.slack_status,
      retryable: envelope.retryable,
      retry_after_seconds: envelope.retry_after_seconds,
      error_code: envelope.error_code,
      contact_checkpoint_present: typeof envelope.remote_contact_id === 'string' && envelope.remote_contact_id !== '',
      deal_checkpoint_present: typeof envelope.remote_deal_id === 'string' && envelope.remote_deal_id !== '',
      slack_timestamp_present: typeof envelope.slack_message_ts === 'string' && envelope.slack_message_ts !== '',
    } : null,
  });
}
process.stdout.write(JSON.stringify(output));
"""

NODE_PROTECTED_ENVELOPE_SANITIZER = r"""
const fs = require('fs');
const crypto = require('crypto');
const { parse } = require('/usr/local/lib/node_modules/n8n/node_modules/.pnpm/flatted@3.4.2/node_modules/flatted');
const [inputPath, targetHash] = process.argv.slice(1);
const records = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
const digest = value => crypto.createHash('sha256').update(value, 'utf8').digest('hex');
const jsonItems = runs => (runs || []).flatMap(run => (run?.data?.main || []).flatMap(branch => (branch || []).map(item => item?.json).filter(Boolean)));
const findEnvelope = (value, seen = new Set(), depth = 0) => {
  if (!value || typeof value !== 'object' || depth > 10 || seen.has(value)) return null;
  seen.add(value);
  if (typeof value.event_key === 'string' && typeof value.result === 'string' && typeof value.processing_phase === 'string') return value;
  for (const child of Object.values(value)) {
    const found = findEnvelope(child, seen, depth + 1);
    if (found) return found;
  }
  return null;
};
const output = [];
for (const record of records) {
  const decoded = parse(record.data);
  const runData = decoded?.resultData?.runData || {};
  let envelope = null;
  for (const runs of Object.values(runData)) {
    for (const item of jsonItems(runs)) envelope = findEnvelope(item) || envelope;
  }
  if (!envelope || digest(envelope.event_key) !== targetHash) continue;
  output.push({
    execution_id: Number(record.id),
    result: envelope.result,
    processing_phase: envelope.processing_phase,
    remote_contact_id: envelope.remote_contact_id,
    remote_deal_id: envelope.remote_deal_id,
    slack_status: envelope.slack_status,
    slack_message_ts: envelope.slack_message_ts,
  });
}
process.stdout.write(JSON.stringify(output));
"""


class ProbeRuntime:
    def __init__(self) -> None:
        self.root = Path(os.environ.get("PF07_RUNTIME_ROOT", "")).resolve()
        self.project = os.environ.get("PF07_COMPOSE_PROJECT", "pf07-orderops-restored")
        self.compose_file = Path(os.environ.get("PF07_COMPOSE_FILE", self.root / "infra/compose.yaml")).resolve()
        self.env_file = Path(os.environ.get("PF07_RUNTIME_ENV", self.root / "runtime/runtime.env")).resolve()
        self.output_dir = Path(os.environ.get("PF07_EVIDENCE_OUTPUT_DIR", "")).resolve()
        self.scratch_root = Path(os.environ.get("PF07_SCRATCH_ROOT", Path.home() / "tmp")).expanduser().resolve()
        if not self.root.is_dir() or not self.compose_file.is_file() or not self.env_file.is_file():
            raise ProbeRuntimeError("restored runtime inputs are missing")
        if not self.output_dir.is_dir():
            raise ProbeRuntimeError("PF07_EVIDENCE_OUTPUT_DIR is missing")
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,62}", self.project) is None:
            raise ProbeRuntimeError("PF07_COMPOSE_PROJECT is invalid")
        self.scratch_root.mkdir(parents=True, exist_ok=True)
        self.env = parse_env_file(self.env_file)
        self.compose = [
            "docker", "compose", "--env-file", str(self.env_file), "-f", str(self.compose_file),
            "-p", self.project, "--profile", "tools",
        ]
        self.n8n_container = f"{self.project}-n8n-1"

    def wpcli(self, arguments: list[str], *, timeout: int = 360) -> subprocess.CompletedProcess[str]:
        return run(
            self.wpcli_command(arguments),
            timeout=timeout,
            label="protected WP-CLI acceptance probe",
        )

    def wpcli_command(self, arguments: list[str], *, service_environment: dict[str, str] | None = None) -> list[str]:
        command = self.compose + ["run", "--rm", "-T"]
        for key, value in sorted((service_environment or {}).items()):
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", key) is None or "\n" in value:
                raise ProbeRuntimeError("WP-CLI service environment override is invalid")
            command += ["-e", f"{key}={value}"]
        return command + ["wpcli", *arguments]

    def start_wpcli(
        self,
        arguments: list[str],
        *,
        service_environment: dict[str, str] | None = None,
    ) -> subprocess.Popen[str]:
        return subprocess.Popen(
            self.wpcli_command(arguments, service_environment=service_environment),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def start_named_wpcli(
        self,
        arguments: list[str],
        container_name: str,
        *,
        service_environment: dict[str, str] | None = None,
    ) -> subprocess.Popen[str]:
        if re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,62}", container_name) is None:
            raise ProbeRuntimeError("named crash-probe container is invalid")
        command = self.compose + ["run", "--rm", "--name", container_name, "-T"]
        for key, value in sorted((service_environment or {}).items()):
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", key) is None or "\n" in value:
                raise ProbeRuntimeError("WP-CLI service environment override is invalid")
            command += ["-e", f"{key}={value}"]
        return subprocess.Popen(
            command + ["wpcli", *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @staticmethod
    def interrupt_named_wpcli(process: subprocess.Popen[str], container_name: str) -> None:
        stopped = subprocess.run(
            ["docker", "kill", container_name],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if stopped.returncode != 0:
            raise ProbeRuntimeError("named crash-probe container could not be stopped")
        try:
            process.communicate(timeout=60)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.communicate()
            raise ProbeRuntimeError("named crash-probe launcher did not terminate") from error
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    @staticmethod
    def finish_wpcli(process: subprocess.Popen[str], label: str, timeout: int = 360) -> None:
        try:
            _stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.communicate()
            raise ProbeRuntimeError(f"{label} timed out") from error
        if process.returncode != 0:
            lines = [line.strip() for line in stderr.splitlines() if line.strip()]
            detail = _redact(lines[-1] if lines else "no diagnostic")
            raise ProbeRuntimeError(f"{label} failed with exit code {process.returncode}: {detail}")

    def wpcli_json(self, arguments: list[str], *, timeout: int = 360) -> object:
        return parse_json_output(self.wpcli(arguments, timeout=timeout), "protected WP-CLI acceptance probe")

    def assert_run_identity(self) -> None:
        expected = os.environ.get("ODDROOM_RUN_ID", "")
        observed = self.wpcli_json([
            "eval",
            "echo wp_json_encode(['run_id'=>OddRoom_Repository::requiredConfig('ODDROOM_ORDEROPS_RUN_ID')]);",
        ])
        if not isinstance(observed, dict) or observed.get("run_id") != expected:
            raise ProbeRuntimeError("collector RUN_ID differs from the active restored runtime")

    def create_order(self, shape: str, alias: str, amount: str) -> dict:
        value = self.wpcli_json([
            "oddroom-orderops", "create-order", f"--shape={shape}", f"--alias={alias}", f"--amount={amount}",
        ])
        if not isinstance(value, dict):
            raise ProbeRuntimeError("synthetic order creation did not return an object")
        for key in ("order_id", "product_id", "outbox_id", "action_id"):
            if not isinstance(value.get(key), int) or value[key] < 1:
                raise ProbeRuntimeError("synthetic order creation returned an invalid identity")
        return value

    def run_action(self, action_id: int) -> None:
        if action_id < 1:
            raise ProbeRuntimeError("invalid Action Scheduler identity")
        self.wpcli(["action-scheduler", "action", "run", str(action_id)], timeout=420)

    def order_rows(self, order_ids: list[int], event_type: str = "ORDER_CREATED") -> dict:
        if not order_ids or any(not isinstance(value, int) or value < 1 for value in order_ids):
            raise ProbeRuntimeError("invalid order identity inventory")
        ids = ",".join(str(value) for value in order_ids)
        code = f"""
$ids=[{ids}];
$adminAll=array_map('intval',wc_get_orders(['limit'=>-1,'return'=>'ids','orderby'=>'ID','order'=>'ASC']));
$admin=array_values(array_intersect($ids,$adminAll));
$storage=[];$rows=[];
foreach($ids as $id){{
  $order=wc_get_order($id);
  if($order instanceof WC_Order){{$storage[]=(int)$order->get_id();}}
  $row=OddRoom_Repository::findEvent($id,'{event_type}');
  if(!$row){{throw new RuntimeException('ROW_NOT_FOUND');}}
  $rows[]=[
    'order_id'=>$id,
    'outbox_id'=>(int)$row->id,
    'event_type'=>(string)$row->event_type,
    'state_rank'=>(int)$row->state_rank,
    'event_key'=>(string)$row->event_key,
    'payload_json'=>(string)$row->payload_json,
    'stored_payload_hash'=>(string)$row->payload_hash,
    'status'=>(string)$row->status,
    'phase'=>(string)$row->processing_phase,
    'action_id'=>$row->action_id===null?null:(int)$row->action_id,
  ];
}}
echo wp_json_encode(['admin_order_ids'=>$admin,'storage_order_ids'=>$storage,'rows'=>$rows],JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);
"""
        value = self.wpcli_json(["eval", code])
        if not isinstance(value, dict) or not isinstance(value.get("rows"), list):
            raise ProbeRuntimeError("order/outbox observation did not return its exact inventory")
        return value

    def row_lock_state(self, row_id: int) -> dict:
        if row_id < 1:
            raise ProbeRuntimeError("invalid outbox row identity")
        code = f"""
global $wpdb;
$row=OddRoom_Repository::find({row_id});
if(!$row){{throw new RuntimeException('ROW_NOT_FOUND');}}
$leases=OddRoom_Installer::leaseTable();
echo wp_json_encode([
  'status'=>(string)$row->status,
  'phase'=>(string)$row->processing_phase,
  'attempt_count'=>(int)$row->attempt_count,
  'automatic_attempt_count'=>(int)$row->automatic_attempt_count,
  'max_attempts'=>(int)$row->max_attempts,
  'manual_retry_count'=>(int)$row->manual_retry_count,
  'manual_attempt_pending'=>(int)$row->manual_attempt_pending,
  'adapter_dispatch_state'=>(string)$row->adapter_dispatch_state,
  'adapter_dispatch_attempt'=>(int)$row->adapter_dispatch_attempt,
  'error_code'=>$row->error_code===null?null:(string)$row->error_code,
  'operator_wait_epoch'=>(int)$row->operator_wait_epoch,
  'resolved_operator_wait_epoch'=>(int)$row->resolved_operator_wait_epoch,
  'last_operator_resolution'=>$row->last_operator_resolution===null?null:(string)$row->last_operator_resolution,
  'next_attempt_due'=>$row->next_attempt_at===null?null:(int)$wpdb->get_var($wpdb->prepare('SELECT %s<=UTC_TIMESTAMP(6)',(string)$row->next_attempt_at)),
  'scheduled_delay_seconds'=>$row->next_attempt_at===null?null:(int)round(((int)$wpdb->get_var($wpdb->prepare('SELECT TIMESTAMPDIFF(MICROSECOND,updated_at,next_attempt_at) FROM '.OddRoom_Installer::outboxTable().' WHERE id=%d',{row_id})))/1000000),
  'row_lock_count'=>$row->lock_token===null?0:1,
  'lock_token_sha256'=>$row->lock_token===null?null:hash('sha256',(string)$row->lock_token),
  'order_lease_count'=>(int)$wpdb->get_var($wpdb->prepare('SELECT COUNT(*) FROM '.$leases.' WHERE holder_outbox_id=%d',{row_id})),
  'action_id'=>$row->action_id===null?null:(int)$row->action_id,
  'candidate_action_ids'=>array_values(array_map('intval',OddRoom_Scheduler::exactCandidates(OddRoom_Scheduler::HOOK,{row_id}))),
  'payload_json'=>(string)$row->payload_json,
  'payload_hash'=>(string)$row->payload_hash,
  'contact_checkpoint_sha256'=>$row->remote_contact_id===null?null:hash('sha256',(string)$row->remote_contact_id),
  'deal_checkpoint_sha256'=>$row->remote_deal_id===null?null:hash('sha256',(string)$row->remote_deal_id),
  'slack_timestamp_sha256'=>$row->slack_message_ts===null?null:hash('sha256',(string)$row->slack_message_ts),
],JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);
"""
        value = self.wpcli_json(["eval", code])
        if not isinstance(value, dict):
            raise ProbeRuntimeError("row lock observation did not return an object")
        return value

    def wait_for_claim(self, row_id: int, timeout: int = 45) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            state = self.row_lock_state(row_id)
            if state.get("row_lock_count") == 1 and state.get("order_lease_count") == 1:
                return state
            if time.monotonic() >= deadline:
                raise ProbeRuntimeError("worker claim/lease observation timed out")
            time.sleep(0.25)

    def wait_for_dispatch(self, row_id: int, timeout: int = 45) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            state = self.row_lock_state(row_id)
            if (
                state.get("adapter_dispatch_state") == "in_flight"
                and state.get("row_lock_count") == 1
                and state.get("order_lease_count") == 1
            ):
                return state
            if time.monotonic() >= deadline:
                raise ProbeRuntimeError("worker in-flight dispatch observation timed out")
            time.sleep(0.25)

    @contextmanager
    def n8n_snapshot(self):
        directory = Path(tempfile.mkdtemp(prefix="pf07-n8n-snapshot-", dir=self.scratch_root))
        paused = False
        try:
            run(["docker", "pause", self.n8n_container], label="n8n snapshot pause")
            paused = True
            for name in ("database.sqlite", "database.sqlite-wal", "database.sqlite-shm"):
                result = subprocess.run(
                    ["docker", "cp", f"{self.n8n_container}:/home/node/.n8n/{name}", str(directory / name)],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if name == "database.sqlite" and result.returncode != 0:
                    raise ProbeRuntimeError("n8n database snapshot failed")
            run(["docker", "unpause", self.n8n_container], label="n8n snapshot unpause")
            paused = False
            yield directory / "database.sqlite"
        finally:
            if paused:
                subprocess.run(["docker", "unpause", self.n8n_container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            shutil.rmtree(directory, ignore_errors=True)

    @staticmethod
    def max_execution(database: Path) -> int:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            return int(connection.execute("SELECT COALESCE(MAX(id),0) FROM execution_entity").fetchone()[0])
        finally:
            connection.close()

    def execution_details(self, database: Path, *, minimum_id: int = 0, exact_ids: list[int] | None = None) -> list[dict]:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            if exact_ids is None:
                rows = connection.execute(
                    "SELECT e.id,e.status,e.startedAt,e.stoppedAt,d.data FROM execution_entity e JOIN execution_data d ON d.executionId=e.id WHERE e.id>? ORDER BY e.id",
                    (minimum_id,),
                ).fetchall()
            elif not exact_ids:
                rows = []
            else:
                placeholders = ",".join("?" for _ in exact_ids)
                rows = connection.execute(
                    f"SELECT e.id,e.status,e.startedAt,e.stoppedAt,d.data FROM execution_entity e JOIN execution_data d ON d.executionId=e.id WHERE e.id IN ({placeholders}) ORDER BY e.id",
                    exact_ids,
                ).fetchall()
        finally:
            connection.close()
        records = [
            {"id": row[0], "status": row[1], "startedAt": row[2], "stoppedAt": row[3], "data": row[4]}
            for row in rows
        ]
        local_name = f"pf07-execution-sanitize-{uuid.uuid4().hex}.json"
        local_path = self.output_dir / local_name
        container_path = f"/tmp/{local_name}"
        local_path.write_text(json.dumps(records, separators=(",", ":")), encoding="utf-8")
        try:
            run(["docker", "cp", str(local_path), f"{self.n8n_container}:{container_path}"], label="n8n sanitizer input copy")
            result = run(
                ["docker", "exec", self.n8n_container, "node", "-e", NODE_EXECUTION_SANITIZER, container_path],
                label="n8n execution sanitizer",
            )
            value = parse_json_output(result, "n8n execution sanitizer")
            if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
                raise ProbeRuntimeError("n8n execution sanitizer returned an invalid collection")
            return value
        finally:
            local_path.unlink(missing_ok=True)
            subprocess.run(["docker", "exec", self.n8n_container, "rm", "-f", container_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    def protected_execution_envelope(self, baseline: int, event_key: str) -> dict:
        target_hash = self.event_key_sha256(event_key)
        with self.n8n_snapshot() as database:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            try:
                rows = connection.execute(
                    "SELECT e.id,e.status,e.startedAt,e.stoppedAt,d.data FROM execution_entity e JOIN execution_data d ON d.executionId=e.id WHERE e.id>? ORDER BY e.id",
                    (baseline,),
                ).fetchall()
            finally:
                connection.close()
        records = [
            {"id": row[0], "status": row[1], "startedAt": row[2], "stoppedAt": row[3], "data": row[4]}
            for row in rows
        ]
        local_name = f"pf07-protected-envelope-{uuid.uuid4().hex}.json"
        local_path = self.output_dir / local_name
        container_path = f"/tmp/{local_name}"
        local_path.write_text(json.dumps(records, separators=(",", ":")), encoding="utf-8")
        try:
            run(["docker", "cp", str(local_path), f"{self.n8n_container}:{container_path}"], label="protected envelope input copy")
            result = run(
                ["docker", "exec", self.n8n_container, "node", "-e", NODE_PROTECTED_ENVELOPE_SANITIZER, container_path, target_hash],
                label="protected envelope extraction",
            )
            value = parse_json_output(result, "protected envelope extraction")
            if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
                raise ProbeRuntimeError("protected execution envelope did not resolve exactly once")
            return value[0]
        finally:
            local_path.unlink(missing_ok=True)
            subprocess.run(["docker", "exec", self.n8n_container, "rm", "-f", container_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    def latest_execution_id(self) -> int:
        with self.n8n_snapshot() as database:
            return self.max_execution(database)

    def execution_state(self) -> dict[str, int]:
        with self.n8n_snapshot() as database:
            maximum = self.max_execution(database)
            details = self.execution_details(database, minimum_id=0)
        return {
            "n8n_execution": maximum,
            "hubspot_calls": sum(int(item["hubspot_outbound_call_count"]) for item in details),
            "association_calls": sum(int(item["association_outbound_call_count"]) for item in details),
            "slack_calls": sum(int(item["slack_outbound_call_count"]) for item in details),
        }

    def new_execution_details(self, baseline: int, expected: int) -> list[dict]:
        deadline = time.monotonic() + 30
        while True:
            with self.n8n_snapshot() as database:
                maximum = self.max_execution(database)
                if maximum - baseline >= expected:
                    details = self.execution_details(database, minimum_id=baseline)
                    if len(details) >= expected:
                        return details
            if time.monotonic() >= deadline:
                raise ProbeRuntimeError("n8n execution observation timed out")
            time.sleep(0.5)

    def wait_for_event_executions(self, baseline: int, event_key: str, expected: int = 1, timeout: int = 45) -> list[dict]:
        if expected < 1:
            raise ProbeRuntimeError("event execution cardinality is invalid")
        target = self.event_key_sha256(event_key)
        deadline = time.monotonic() + timeout
        while True:
            with self.n8n_snapshot() as database:
                details = self.execution_details(database, minimum_id=baseline)
            matches = [item for item in details if item.get("event_key_sha256") == target]
            if len(matches) >= expected:
                return matches
            if time.monotonic() >= deadline:
                raise ProbeRuntimeError("event-key-filtered n8n execution observation timed out")
            time.sleep(0.5)

    @staticmethod
    def event_key_sha256(event_key: str) -> str:
        return hashlib.sha256(event_key.encode("utf-8")).hexdigest()
