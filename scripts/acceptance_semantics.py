from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Callable


class AcceptanceSemanticError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceSemanticError(message)


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceSemanticError(f"cannot read semantic artifact {path.name}: {error}") from error
    _require(isinstance(value, dict), f"semantic artifact root is not an object: {path.name}")
    return value


def _exact(value: dict, keys: set[str], label: str) -> None:
    _require(set(value) == keys, f"{label} fields differ: {sorted(set(value) ^ keys)}")


def _integer(value: object, label: str, minimum: int = 0) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool) and value >= minimum, f"{label} is not a bounded integer")
    return value


def _sha(value: object, label: str) -> str:
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None, f"{label} is not SHA-256")
    return value


def _payload(item: dict, label: str) -> dict:
    _exact(item, {"payload_json", "stored_payload_hash"}, label)
    payload = item["payload_json"]
    _require(isinstance(payload, str) and payload.startswith("{") and payload.endswith("}"), f"{label} canonical payload is missing")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    _require(_sha(item["stored_payload_hash"], f"{label}.stored_payload_hash") == digest, f"{label} immutable payload hash differs")
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as error:
        raise AcceptanceSemanticError(f"{label} payload is not JSON: {error.msg}") from error
    _require(isinstance(decoded, dict), f"{label} payload root is not an object")
    return decoded


def _root(value: dict, fixture_id: str, keys: set[str]) -> None:
    _exact(value, {"schema_version", "fixture_id", *keys}, fixture_id)
    _require(value["schema_version"] == 1 and value["fixture_id"] == fixture_id, f"{fixture_id} artifact identity differs")


def _normal_order(path: Path) -> dict:
    value = _load(path)
    _root(value, "normal-order", {"orders", "admin_order_ids", "storage_order_ids"})
    orders = value["orders"]
    _require(isinstance(orders, list) and len(orders) == 3, "GATE-01 must contain exactly three orders")
    shapes: list[str] = []
    order_ids: list[int] = []
    payload_hashes: set[str] = set()
    execution_ids: set[int] = set()
    signed_requests = 0
    fixed_hubspot_paths = 0
    completed_envelopes = 0
    persisted_deal_checkpoints = 0
    hashes_valid = True
    for index, order in enumerate(orders):
        _require(isinstance(order, dict), "GATE-01 order is not an object")
        _exact(order, {"order_id", "product_id", "variation_id", "shape", "coupon_applied", "payload", "execution"}, f"GATE-01 order {index}")
        order_id = _integer(order["order_id"], "GATE-01 order_id", 1)
        _integer(order["product_id"], "GATE-01 product_id", 1)
        variation_id = _integer(order["variation_id"], "GATE-01 variation_id")
        shape = order["shape"]
        _require(shape in {"simple", "variable", "coupon"}, "GATE-01 order shape is invalid")
        _require(isinstance(order["coupon_applied"], bool), "GATE-01 coupon observation is not boolean")
        _require((shape == "variable") == (variation_id > 0), "GATE-01 variation identity differs from shape")
        _require((shape == "coupon") == order["coupon_applied"], "GATE-01 coupon fact differs from shape")
        _require(isinstance(order["payload"], dict), "GATE-01 payload commitment is missing")
        _payload(order["payload"], f"GATE-01 order {index}")
        payload_hash = _sha(order["payload"]["stored_payload_hash"], f"GATE-01 payload hash {index}")
        payload_hashes.add(payload_hash)
        execution = order["execution"]
        _require(isinstance(execution, dict), "GATE-01 execution observation is missing")
        _exact(
            execution,
            {
                "execution_id", "verified_authorized", "ingress_raw_body_sha256", "verified_payload_sha256",
                "executed_hubspot_nodes", "envelope_result", "envelope_phase",
                "envelope_deal_checkpoint_present", "wordpress_status", "wordpress_phase",
                "wordpress_deal_checkpoint_present",
            },
            f"GATE-01 execution {index}",
        )
        execution_ids.add(_integer(execution["execution_id"], "GATE-01 execution_id", 1))
        exact_signed = (
            execution["verified_authorized"] is True
            and _sha(execution["ingress_raw_body_sha256"], "GATE-01 ingress body") == payload_hash
            and _sha(execution["verified_payload_sha256"], "GATE-01 verified payload") == payload_hash
        )
        signed_requests += int(exact_signed)
        expected_hubspot_nodes = [
            "HubSpot 2026-03 Deal Read",
            "HubSpot 2026-03 Deal Readback",
            "HubSpot 2026-03 Deal Upsert",
        ]
        fixed_hubspot_paths += int(execution["executed_hubspot_nodes"] == expected_hubspot_nodes)
        completed_envelopes += int(
            execution["envelope_result"] == "completed"
            and execution["envelope_phase"] == "completed"
            and execution["envelope_deal_checkpoint_present"] is True
        )
        persisted_deal_checkpoints += int(
            execution["wordpress_status"] == "completed"
            and execution["wordpress_phase"] == "completed"
            and execution["wordpress_deal_checkpoint_present"] is True
        )
        shapes.append(shape)
        order_ids.append(order_id)
    _require(len(set(order_ids)) == 3, "GATE-01 order identities are not distinct")
    _require(len(execution_ids) == 3, "GATE-01 execution identities are not distinct")
    admin_ids = value["admin_order_ids"]
    storage_ids = value["storage_order_ids"]
    _require(isinstance(admin_ids, list) and isinstance(storage_ids, list), "GATE-01 admin/storage observations are missing")
    observed = sorted(admin_ids) == sorted(order_ids) == sorted(storage_ids)
    return {
        "simple_product_orders": shapes.count("simple"),
        "variable_product_orders": shapes.count("variable"),
        "coupon_orders": shapes.count("coupon"),
        "woocommerce_admin_and_storage_observed": observed,
        "immutable_payload_hashes_valid": hashes_valid,
        "distinct_payload_hash_count": len(payload_hashes),
        "signed_request_count": signed_requests,
        "fixed_hubspot_path_execution_count": fixed_hubspot_paths,
        "completed_envelope_count": completed_envelopes,
        "persisted_deal_checkpoint_count": persisted_deal_checkpoints,
    }


def _variable_input(path: Path) -> dict:
    value = _load(path)
    _root(value, "variable-input", {"orders"})
    orders = value["orders"]
    _require(isinstance(orders, list) and len(orders) == 3, "GATE-03 must contain exactly three workflow inputs")
    order_ids: set[int] = set()
    customers: set[str] = set()
    products: set[str] = set()
    payload_hashes: set[str] = set()
    executions: set[int] = set()
    exact_inputs = True
    for index, order in enumerate(orders):
        _require(isinstance(order, dict), "GATE-03 input is not an object")
        _exact(order, {"order_id", "execution_id", "verified_payload_sha256", "payload"}, f"GATE-03 input {index}")
        order_ids.add(_integer(order["order_id"], "GATE-03 order_id", 1))
        executions.add(_integer(order["execution_id"], "GATE-03 execution_id", 1))
        decoded = _payload(order["payload"], f"GATE-03 input {index}")
        digest = order["payload"]["stored_payload_hash"]
        exact_inputs = exact_inputs and _sha(order["verified_payload_sha256"], "GATE-03 verified payload hash") == digest
        order_input = decoded.get("order")
        _require(isinstance(order_input, dict), "GATE-03 order input is missing")
        customer = order_input.get("customer")
        items = order_input.get("items")
        _require(isinstance(customer, dict) and isinstance(customer.get("email"), str), "GATE-03 customer input is missing")
        _require(isinstance(items, list) and bool(items), "GATE-03 product input is missing")
        customers.add(customer["email"])
        products.add(hashlib.sha256(json.dumps(items, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest())
        payload_hashes.add(digest)
    fixed_fixture_used = not (exact_inputs and len(executions) == 3 and len(payload_hashes) == 3)
    return {
        "distinct_order_count": len(order_ids),
        "distinct_customer_alias_count": len(customers),
        "distinct_product_input_count": len(products),
        "distinct_payload_hash_count": len(payload_hashes),
        "fixed_workflow_fixture_used": fixed_fixture_used,
    }


def _state_non_regression(path: Path) -> dict:
    value = _load(path)
    _root(value, "state-non-regression", {"events", "concurrent_claim", "delayed_lower_rank", "authoritative_readback"})
    events = value["events"]
    expected_ranks = {"ORDER_CREATED": 10, "PAYMENT_CONFIRMED": 20, "ORDER_CANCELLED": 30, "ORDER_REFUNDED": 40}
    _require(isinstance(events, list) and len(events) == 4, "GATE-02 four-event trace cardinality differs")
    ranks: list[int] = []
    for index, event in enumerate(events):
        _require(isinstance(event, dict), "GATE-02 event is not an object")
        _exact(event, {"event_type", "state_rank", "payload", "execution_result"}, f"GATE-02 event {index}")
        event_type = event["event_type"]
        rank = _integer(event["state_rank"], "GATE-02 state rank", 1)
        _require(expected_ranks.get(event_type) == rank, "GATE-02 event rank differs from the contract")
        _require(isinstance(event["payload"], dict), "GATE-02 payload commitment is missing")
        _payload(event["payload"], f"GATE-02 event {index}")
        _require(event["execution_result"] in {"completed", "stale_ignored"}, "GATE-02 execution result is invalid")
        ranks.append(rank)
    _require({event["event_type"] for event in events} == set(expected_ranks), "GATE-02 event type set differs")
    claim = value["concurrent_claim"]
    _require(isinstance(claim, dict), "GATE-02 concurrent claim is missing")
    _exact(claim, {"worker_invocations", "row_claim_owners", "order_lease_owners", "adapter_dispatches"}, "GATE-02 concurrent claim")
    _require(
        _integer(claim["worker_invocations"], "GATE-02 worker invocations") == 2
        and _integer(claim["row_claim_owners"], "GATE-02 row claim owners") == 1
        and _integer(claim["order_lease_owners"], "GATE-02 lease owners") == 1
        and _integer(claim["adapter_dispatches"], "GATE-02 adapter dispatches") == 1,
        "GATE-02 same-order serialization failed",
    )
    delayed = value["delayed_lower_rank"]
    _require(isinstance(delayed, list) and len(delayed) == 2, "GATE-02 delayed lower-rank trace differs")
    _require({entry.get("event_type") for entry in delayed if isinstance(entry, dict)} == {"ORDER_CREATED", "PAYMENT_CONFIRMED"}, "GATE-02 delayed event set differs")
    rank_regressions = 0
    pipeline_regressions = 0
    delayed_results = 0
    delayed_payment_slack = 0
    for entry in delayed:
        _exact(entry, {"event_type", "result", "slack_calls", "rank_before", "rank_after", "pipeline_before", "pipeline_after"}, "GATE-02 delayed event")
        _require(entry["result"] == "stale_ignored", "GATE-02 delayed event was not stale-ignored")
        delayed_results += 1
        calls = _integer(entry["slack_calls"], "GATE-02 delayed Slack calls")
        if entry["event_type"] == "PAYMENT_CONFIRMED":
            delayed_payment_slack += calls
        before = _integer(entry["rank_before"], "GATE-02 rank before", 1)
        after = _integer(entry["rank_after"], "GATE-02 rank after", 1)
        rank_regressions += int(after < before)
        _require(isinstance(entry["pipeline_before"], str) and isinstance(entry["pipeline_after"], str), "GATE-02 pipeline readback is missing")
        pipeline_regressions += int(entry["pipeline_before"] != entry["pipeline_after"])
    readback = value["authoritative_readback"]
    _require(isinstance(readback, dict), "GATE-02 authoritative readback is missing")
    _exact(readback, {"state_rank", "pipeline"}, "GATE-02 authoritative readback")
    _require(_integer(readback["state_rank"], "GATE-02 authoritative rank") == 40 and isinstance(readback["pipeline"], str) and readback["pipeline"], "GATE-02 authoritative state is not refunded")
    return {
        "event_type_count": len(events),
        "event_state_ranks": sorted(ranks),
        "delayed_lower_rank_results": delayed_results,
        "delayed_payment_slack_calls": delayed_payment_slack,
        "authoritative_rank_regressions": rank_regressions,
        "pipeline_regressions": pipeline_regressions,
    }


def _duplicate(path: Path) -> dict:
    value = _load(path)
    _root(value, "concurrent-duplicate-suppression", {"worker_invocations", "immutable_rows", "manual_retry", "n8n_executions", "hubspot_readback"})
    workers = value["worker_invocations"]
    _require(isinstance(workers, list) and len(workers) == 3, "GATE-04 worker cardinality differs")
    for worker in workers:
        _exact(worker, {"invocation_id", "row_claim_owned", "order_lease_owned", "adapter_dispatched"}, "GATE-04 worker")
        _integer(worker["invocation_id"], "GATE-04 invocation identity", 1)
        _require(all(isinstance(worker[key], bool) for key in ("row_claim_owned", "order_lease_owned", "adapter_dispatched")), "GATE-04 worker ownership fields are invalid")
    rows = value["immutable_rows"]
    _require(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict), "GATE-04 immutable row cardinality differs")
    _exact(rows[0], {"outbox_id", "payload"}, "GATE-04 immutable row")
    _integer(rows[0]["outbox_id"], "GATE-04 outbox identity", 1)
    _payload(rows[0]["payload"], "GATE-04 immutable row")
    retry = value["manual_retry"]
    _require(isinstance(retry, dict), "GATE-04 manual retry is missing")
    _exact(retry, {"attempted_during_claim", "outcome", "lock_token_sha256_before", "lock_token_sha256_after"}, "GATE-04 manual retry")
    _require(retry["attempted_during_claim"] is True and retry["outcome"] == "conflict", "GATE-04 manual retry did not conflict during claim")
    _require(_sha(retry["lock_token_sha256_before"], "GATE-04 lock before") == _sha(retry["lock_token_sha256_after"], "GATE-04 lock after"), "GATE-04 manual retry changed the live lock")
    executions = value["n8n_executions"]
    _require(isinstance(executions, list) and len(executions) == 1, "GATE-04 n8n execution cardinality differs")
    execution = executions[0]
    _exact(execution, {"execution_id", "status", "slack_outbound_call_count", "returned_slack_timestamp_present"}, "GATE-04 n8n execution")
    _integer(execution["execution_id"], "GATE-04 execution identity", 1)
    _require(execution["status"] == "success", "GATE-04 n8n execution did not succeed")
    hubspot = value["hubspot_readback"]
    _require(isinstance(hubspot, dict) and set(hubspot) == {"deal_count"}, "GATE-04 HubSpot readback shape differs")
    return {
        "concurrent_workers": len(workers),
        "row_claim_owners": sum(int(worker["row_claim_owned"]) for worker in workers),
        "order_lease_owners": sum(int(worker["order_lease_owned"]) for worker in workers),
        "manual_retry_conflicts": 1,
        "immutable_row_count": len(rows),
        "deal_count": _integer(hubspot["deal_count"], "GATE-04 deal count"),
        "slack_post_count": _integer(execution["slack_outbound_call_count"], "GATE-04 Slack count"),
        "returned_slack_timestamp_count": int(execution["returned_slack_timestamp_present"] is True),
    }


def _hmac(path: Path) -> dict:
    value = _load(path)
    _root(value, "hmac-rejection", {"rejected_cases", "valid_exact_bytes"})
    cases = value["rejected_cases"]
    expected = {"missing_signature", "mutated_body", "expired_timestamp"}
    _require(isinstance(cases, list) and len(cases) == 3, "GATE-05 rejected case cardinality differs")
    external_calls = 0
    flags: dict[str, bool] = {}
    for case in cases:
        _exact(case, {"name", "http_status", "executed_nodes", "hubspot_calls", "association_calls", "slack_calls", "deal_count"}, "GATE-05 rejected case")
        name = case["name"]
        _require(name in expected, "GATE-05 rejected case name differs")
        status = _integer(case["http_status"], "GATE-05 rejected status")
        nodes = case["executed_nodes"]
        _require(400 <= status < 500 and isinstance(nodes, list) and bool(nodes) and all(isinstance(node, str) for node in nodes), "GATE-05 rejection trace is incomplete")
        calls = sum(_integer(case[key], f"GATE-05 {key}") for key in ("hubspot_calls", "association_calls", "slack_calls"))
        external_calls += calls
        _require(_integer(case["deal_count"], "GATE-05 rejected Deal count") == 0, "GATE-05 rejected fixture created a Deal")
        flags[name] = status >= 400 and status < 500 and calls == 0
    _require(set(flags) == expected, "GATE-05 rejected case set differs")
    valid = value["valid_exact_bytes"]
    _exact(valid, {"http_status", "body_sha256", "authenticated_body_sha256", "non_ascii_present", "insignificant_whitespace_present"}, "GATE-05 exact-byte case")
    valid_exact = (
        _integer(valid["http_status"], "GATE-05 valid status") == 200
        and _sha(valid["body_sha256"], "GATE-05 body hash") == _sha(valid["authenticated_body_sha256"], "GATE-05 authenticated hash")
        and valid["non_ascii_present"] is True
        and valid["insignificant_whitespace_present"] is True
    )
    return {
        "rejected_case_count": len(cases),
        "missing_signature_rejected": flags["missing_signature"],
        "mutated_body_rejected": flags["mutated_body"],
        "expired_timestamp_rejected": flags["expired_timestamp"],
        "external_call_count": external_calls,
        "valid_exact_whitespace_bytes_accepted": valid_exact,
    }


def _resource(path: Path) -> dict:
    value = _load(path)
    _root(value, "raw-byte-resource-bounds", {"maximum_body_bytes", "oversized", "resource_invalid", "valid_exact_bytes"})
    maximum = _integer(value["maximum_body_bytes"], "GATE-05 maximum body bytes", 1)
    oversized = value["oversized"]
    _exact(oversized, {"sent_bytes", "http_status", "n8n_execution_before", "n8n_execution_after", "hubspot_calls_before", "hubspot_calls_after", "association_calls_before", "association_calls_after", "slack_calls_before", "slack_calls_after"}, "GATE-05 oversized trace")
    before_after = [
        (_integer(oversized[f"{name}_before"], f"GATE-05 oversized {name} before"), _integer(oversized[f"{name}_after"], f"GATE-05 oversized {name} after"))
        for name in ("n8n_execution", "hubspot_calls", "association_calls", "slack_calls")
    ]
    _require(
        _integer(oversized["sent_bytes"], "GATE-05 oversized bytes", 1) == maximum + 1
        and _integer(oversized["http_status"], "GATE-05 oversized status") == 413
        and all(before == after for before, after in before_after),
        "GATE-05 oversized ingress did not reject before every downstream effect",
    )
    invalid = value["resource_invalid"]
    _exact(invalid, {"http_status", "executed_nodes", "hubspot_calls", "association_calls", "slack_calls", "deal_count"}, "GATE-05 resource-invalid trace")
    invalid_calls = sum(_integer(invalid[key], f"GATE-05 resource-invalid {key}") for key in ("hubspot_calls", "association_calls", "slack_calls"))
    _require(400 <= _integer(invalid["http_status"], "GATE-05 resource-invalid status") < 500, "GATE-05 resource-invalid request was not rejected")
    _require(isinstance(invalid["executed_nodes"], list) and bool(invalid["executed_nodes"]), "GATE-05 resource-invalid execution trace is missing")
    _require(_integer(invalid["deal_count"], "GATE-05 resource-invalid Deal count") == 0, "GATE-05 resource-invalid fixture created a Deal")
    valid = value["valid_exact_bytes"]
    _exact(valid, {"http_status", "body_sha256", "authenticated_body_sha256", "non_ascii_present", "insignificant_whitespace_present", "reserialized_old_signature_status"}, "GATE-05 bounded exact-byte trace")
    exact_valid = (
        _integer(valid["http_status"], "GATE-05 bounded valid status") == 200
        and _sha(valid["body_sha256"], "GATE-05 bounded body hash") == _sha(valid["authenticated_body_sha256"], "GATE-05 bounded authenticated hash")
        and valid["non_ascii_present"] is True
        and valid["insignificant_whitespace_present"] is True
        and 400 <= _integer(valid["reserialized_old_signature_status"], "GATE-05 reserialized status") < 500
    )
    return {
        "exact_byte_valid": exact_valid,
        "maximum_body_bytes": maximum,
        "oversized_observed_bytes": _integer(oversized["sent_bytes"], "GATE-05 oversized bytes", 1),
        "oversized_status": _integer(oversized["http_status"], "GATE-05 oversized status"),
        "oversized_workflow_execution_delta": before_after[0][1] - before_after[0][0],
        "resource_invalid_external_calls": invalid_calls,
    }


def _reconciliation(path: Path) -> dict:
    value = _load(path)
    _root(value, "reconciliation-repair", {"repairs", "schedule_repair"})
    repairs = value["repairs"]
    sources = {"ORDER_CREATED": "date_created", "PAYMENT_CONFIRMED": "date_paid", "ORDER_CANCELLED": "_oddroom_orderops_cancelled_at_utc", "ORDER_REFUNDED": "full_refund_completion"}
    _require(isinstance(repairs, list) and len(repairs) == 4, "GATE-08 repair cardinality differs")
    payload_mutations = 0
    second_mutations = 0
    inserted = 0
    scheduled = 0
    for repair in repairs:
        _exact(repair, {"event_type", "fact_source", "before_row_count", "after_first", "after_second"}, "GATE-08 missing-event repair")
        _require(sources.get(repair["event_type"]) == repair["fact_source"], "GATE-08 fact source differs")
        _require(_integer(repair["before_row_count"], "GATE-08 row count before") == 0, "GATE-08 suppressed row already existed")
        snapshots = []
        for label in ("after_first", "after_second"):
            snapshot = repair[label]
            _exact(snapshot, {"row_count", "action_count", "payload"}, f"GATE-08 {label}")
            _require(_integer(snapshot["row_count"], f"GATE-08 {label} row count") == 1 and _integer(snapshot["action_count"], f"GATE-08 {label} action count") == 1, f"GATE-08 {label} did not converge")
            _payload(snapshot["payload"], f"GATE-08 {label}")
            snapshots.append(snapshot)
        inserted += 1
        scheduled += 1
        payload_mutations += int(snapshots[0]["payload"] != snapshots[1]["payload"])
        second_mutations += int(snapshots[0] != snapshots[1])
    _require({repair["event_type"] for repair in repairs} == set(sources), "GATE-08 repaired event set differs")
    schedule = value["schedule_repair"]
    _exact(schedule, {"before", "after_first", "after_second"}, "GATE-08 schedule-only repair")
    schedule_snapshots = []
    for label, expected_actions in (("before", 0), ("after_first", 1), ("after_second", 1)):
        snapshot = schedule[label]
        _exact(snapshot, {"row_count", "action_count", "payload"}, f"GATE-08 schedule {label}")
        _require(_integer(snapshot["row_count"], f"GATE-08 schedule {label} row count") == 1 and _integer(snapshot["action_count"], f"GATE-08 schedule {label} action count") == expected_actions, f"GATE-08 schedule {label} differs")
        _payload(snapshot["payload"], f"GATE-08 schedule {label}")
        schedule_snapshots.append(snapshot)
    payload_mutations += int(len({json.dumps(snapshot["payload"], sort_keys=True) for snapshot in schedule_snapshots}) != 1)
    second_mutations += int(schedule_snapshots[1] != schedule_snapshots[2])
    return {
        "supported_event_types": len(sources),
        "missing_event_repairs": len(repairs),
        "schedule_only_repairs": 1,
        "first_scan_inserted_rows": inserted,
        "first_scan_scheduled_missing_rows": scheduled,
        "second_scan_mutations": second_mutations,
        "payload_mutations": payload_mutations,
        "protected_cancellation_fact_used": any(repair["event_type"] == "ORDER_CANCELLED" and repair["fact_source"] == sources["ORDER_CANCELLED"] for repair in repairs),
    }


def _compatibility(path: Path) -> dict:
    value = _load(path)
    _root(value, "hpos-compatibility", {"environment", "checks"})
    environment = value["environment"]
    _require(isinstance(environment, dict), "GATE-09 environment is missing")
    _exact(environment, {"wordpress", "woocommerce", "php", "action_scheduler_version", "action_scheduler_source", "tables_transactional", "database_utc"}, "GATE-09 environment")
    _require(all(isinstance(environment[key], str) and environment[key] for key in ("wordpress", "woocommerce", "php", "action_scheduler_version", "action_scheduler_source", "database_utc")), "GATE-09 compatibility identity is incomplete")
    _require(environment["tables_transactional"] is True, "GATE-09 PF07 tables are not transactional")
    version_match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", environment["action_scheduler_version"])
    _require(version_match is not None, "GATE-09 Action Scheduler version is invalid")
    version_supported = tuple(map(int, version_match.groups())) >= (4, 0, 0)
    checks = value["checks"]
    _require(isinstance(checks, list), "GATE-09 compatibility checks are missing")
    required = {"hpos_disabled", "hpos_enabled", "activation_dependency_rejection", "migration_idempotence", "uninstall_preserve_default", "uninstall_opt_in_removal", "scheduler_failure_branches"}
    results: dict[str, bool] = {}
    for check in checks:
        _exact(check, {"name", "exit_code", "assertion_count", "failure_count", "details"}, "GATE-09 compatibility check")
        name = check["name"]
        _require(name in required and name not in results, "GATE-09 compatibility check set differs")
        details = check["details"]
        _require(isinstance(details, dict), f"GATE-09 {name} details are missing")
        if name in {"hpos_disabled", "hpos_enabled"}:
            _exact(details, {"hpos_enabled", "outbox_row_present", "payload_hash_valid", "wc_order_readable"}, f"GATE-09 {name} details")
            _require(
                details["hpos_enabled"] is (name == "hpos_enabled")
                and details["outbox_row_present"] is True
                and details["payload_hash_valid"] is True
                and details["wc_order_readable"] is True,
                f"GATE-09 {name} behavior differs",
            )
        elif name == "activation_dependency_rejection":
            _exact(details, {"activation_without_woocommerce_exit", "plugin_active_after_rejection", "pf07_table_count_after_rejection", "activation_after_woocommerce_exit"}, "GATE-09 activation details")
            _require(
                _integer(details["activation_without_woocommerce_exit"], "GATE-09 rejected activation exit", 1) > 0
                and details["plugin_active_after_rejection"] is False
                and _integer(details["pf07_table_count_after_rejection"], "GATE-09 rejection table count") == 0
                and _integer(details["activation_after_woocommerce_exit"], "GATE-09 accepted activation exit") == 0,
                "GATE-09 activation dependency behavior differs",
            )
        elif name == "migration_idempotence":
            _exact(details, {"starting_schema_option", "starting_table_count", "ending_schema_option", "ending_table_count", "tables_innodb", "repeated_schema_unchanged"}, "GATE-09 migration details")
            _require(
                details["starting_schema_option"] == "1.0.0"
                and _integer(details["starting_table_count"], "GATE-09 starting table count") == 2
                and details["ending_schema_option"] == "1.1.0"
                and _integer(details["ending_table_count"], "GATE-09 ending table count") == 3
                and details["tables_innodb"] is True
                and details["repeated_schema_unchanged"] is True,
                "GATE-09 migration behavior differs",
            )
        elif name == "uninstall_preserve_default":
            _exact(details, {"tables_before", "rows_before", "tables_after", "rows_after", "data_preserved"}, "GATE-09 default uninstall details")
            _require(
                _integer(details["tables_before"], "GATE-09 preserved tables before") == 3
                and _integer(details["rows_before"], "GATE-09 preserved rows before", 1) >= 1
                and details["tables_after"] == details["tables_before"]
                and details["rows_after"] == details["rows_before"]
                and details["data_preserved"] is True,
                "GATE-09 default uninstall behavior differs",
            )
        elif name == "uninstall_opt_in_removal":
            _exact(details, {"candidate_actions_before", "candidate_actions_after", "tables_after", "schema_option_after"}, "GATE-09 opt-in uninstall details")
            _require(
                _integer(details["candidate_actions_before"], "GATE-09 candidates before removal", 1) >= 1
                and _integer(details["candidate_actions_after"], "GATE-09 candidates after removal") == 0
                and _integer(details["tables_after"], "GATE-09 tables after removal") == 0
                and details["schema_option_after"] is None,
                "GATE-09 opt-in uninstall behavior differs",
            )
        elif name == "scheduler_failure_branches":
            _exact(details, {"unsupported_version", "stale_preflight", "supported_preflight", "isolated_branch_assertions", "isolated_branch_failures"}, "GATE-09 scheduler details")
            for branch_name, error_code in (("unsupported_version", "ACTION_SCHEDULER_VERSION_UNSUPPORTED"), ("stale_preflight", "ACTION_SCHEDULER_PREFLIGHT_REQUIRED")):
                branch = details[branch_name]
                _require(isinstance(branch, dict), f"GATE-09 {branch_name} is missing")
                _exact(branch, {"returned_action_id", "status", "action_id", "attempt_count", "lease_count", "error_code", "candidate_count"}, f"GATE-09 {branch_name}")
                _require(branch == {"returned_action_id": 0, "status": "pending", "action_id": None, "attempt_count": 0, "lease_count": 0, "error_code": error_code, "candidate_count": 0}, f"GATE-09 {branch_name} behavior differs")
            preflight = details["supported_preflight"]
            _require(isinstance(preflight, dict), "GATE-09 supported preflight is missing")
            _exact(preflight, {"status", "version", "source", "row_101_candidate_count", "row_102_candidate_count", "duplicate_raw_id", "remaining_candidate_count"}, "GATE-09 supported preflight")
            _require(
                preflight["status"] == "PASS"
                and preflight["version"] == environment["action_scheduler_version"]
                and preflight["source"] == environment["action_scheduler_source"]
                and preflight["row_101_candidate_count"] == 1
                and preflight["row_102_candidate_count"] == 1
                and preflight["duplicate_raw_id"] == 0
                and preflight["remaining_candidate_count"] == 0
                and _integer(details["isolated_branch_assertions"], "GATE-09 branch assertions", 20) >= 20
                and _integer(details["isolated_branch_failures"], "GATE-09 branch failures") == 0,
                "GATE-09 scheduler branch behavior differs",
            )
        results[name] = (
            _integer(check["exit_code"], f"GATE-09 {name} exit code") == 0
            and _integer(check["assertion_count"], f"GATE-09 {name} assertion count", 1) > 0
            and _integer(check["failure_count"], f"GATE-09 {name} failures") == 0
        )
    _require(set(results) == required, "GATE-09 compatibility check set is incomplete")
    return {
        "hpos_disabled": "PASS" if results["hpos_disabled"] else "FAIL",
        "hpos_enabled": "PASS" if results["hpos_enabled"] else "FAIL",
        "action_scheduler_version_supported": version_supported,
        "activation_dependency_rejection": "PASS" if results["activation_dependency_rejection"] else "FAIL",
        "migration_idempotent": results["migration_idempotence"],
        "uninstall_preserves_by_default": results["uninstall_preserve_default"],
        "opt_in_removal": "PASS" if results["uninstall_opt_in_removal"] else "FAIL",
        "scheduler_failure_branches": "PASS" if results["scheduler_failure_branches"] else "FAIL",
    }


def _product_quality(path: Path) -> dict:
    value = _load(path)
    _root(value, "product-quality", {"ui_evidence", "machine_checks", "php_log_window"})
    ui = value["ui_evidence"]
    _require(isinstance(ui, dict), "GATE-09 UI evidence is missing")
    _exact(ui, {"storefront", "admin", "failures"}, "GATE-09 UI evidence")
    storefront = ui["storefront"]
    admin = ui["admin"]
    _require(isinstance(storefront, list) and isinstance(admin, list) and isinstance(ui["failures"], list), "GATE-09 UI collections are invalid")
    _require(ui["failures"] == [], "GATE-09 UI runner reported failures")
    viewports = {390, 768, 1440}
    pages = {"home", "shop", "category", "product", "cart", "checkout", "account", "tracking"}
    observed_pairs = [
        (item.get("page"), item.get("viewport_width"))
        for item in storefront
        if isinstance(item, dict)
    ]
    expected_pairs = {(page, viewport) for page in pages for viewport in viewports}
    _require(
        set(observed_pairs) == expected_pairs
        and len(observed_pairs) == len(expected_pairs),
        "GATE-09 storefront coverage differs",
    )
    _require({item.get("viewport_width") for item in admin if isinstance(item, dict)} == {390, 768, 1440} and len(admin) == 3, "GATE-09 admin coverage differs")
    storefront_fields = {
        "page", "viewport_width", "url_alias", "mode", "http_status", "expected_path_reached",
        "moderate_or_worse", "critical_or_serious", "page_overflow_px", "horizontally_clipped_control_count",
        "broken_image_count", "image_without_alt_count", "placeholder_asset_count", "console_errors",
        "failed_resources", "korean_locale", "forbidden_copy", "overlapping_control_count",
        "unlabeled_control_count", "keyboard_inoperable_control_count", "required_font_load_failures",
        "unresolved_skeleton_count", "visible_h1_count", "split_korean_word_count",
    }
    admin_fields = {
        "page", "viewport_width", "url_alias", "mode", "root_selector", "http_status",
        "moderate_or_worse", "critical_or_serious", "console_errors", "table_overflow_contained",
        "horizontally_clipped_action_count", "overlapping_protected_action_count",
        "unlabeled_protected_action_count",
    }
    for item in storefront:
        _require(isinstance(item, dict) and storefront_fields <= set(item), "GATE-09 storefront observation is incomplete")
        _require(item["mode"] == "full_document" and item["http_status"] == 200 and item["expected_path_reached"] is True, "GATE-09 storefront route observation failed")
        _require(isinstance(item["url_alias"], str) and item["url_alias"].startswith("PF07_"), "GATE-09 storefront URL alias is invalid")
    for item in admin:
        _require(isinstance(item, dict) and admin_fields <= set(item), "GATE-09 admin observation is incomplete")
        _require(item["mode"] == "scoped" and item["root_selector"] == ".oddroom-orderops" and item["http_status"] == 200, "GATE-09 admin scope observation failed")
        _require(item["url_alias"] == "PF07_ADMIN", "GATE-09 admin URL alias is invalid")
    all_surfaces = storefront + admin
    moderate = sum(len(item.get("moderate_or_worse", [])) for item in all_surfaces)
    severe = sum(len(item.get("critical_or_serious", [])) for item in all_surfaces)
    overflow = sum(int(item.get("page_overflow_px", 0) > 1) for item in storefront)
    clipped = sum(_integer(item.get("horizontally_clipped_control_count", item.get("horizontally_clipped_action_count", 0)), "GATE-09 clipped controls") for item in all_surfaces)
    broken = sum(_integer(item.get("broken_image_count", 0), "GATE-09 broken images") for item in storefront)
    console = sum(len(item.get("console_errors", [])) for item in all_surfaces)
    overlaps = sum(_integer(item.get("overlapping_control_count", item.get("overlapping_protected_action_count", 0)), "GATE-09 overlapping controls") for item in all_surfaces)
    placeholder = sum(int(item.get("forbidden_copy") is True) + _integer(item.get("placeholder_asset_count", 0), "GATE-09 placeholder assets") for item in storefront)
    locales = sum(int(item.get("korean_locale") is not True) for item in storefront)
    unlabeled = sum(_integer(item.get("unlabeled_control_count", item.get("unlabeled_protected_action_count", 0)), "GATE-09 unlabeled controls") for item in all_surfaces)
    keyboard = sum(_integer(item.get("keyboard_inoperable_control_count", 0), "GATE-09 keyboard controls") for item in storefront)
    fonts = sum(_integer(item.get("required_font_load_failures", 0), "GATE-09 font loads") for item in storefront)
    skeletons = sum(_integer(item.get("unresolved_skeleton_count", 0), "GATE-09 skeletons") for item in storefront)
    headings = sum(int(_integer(item.get("visible_h1_count"), "GATE-09 visible H1 count") != 1) for item in storefront)
    split_korean_words = sum(_integer(item.get("split_korean_word_count"), "GATE-09 split Korean words") for item in storefront)
    alt = sum(_integer(item.get("image_without_alt_count", 0), "GATE-09 image alt") for item in storefront)
    resources = sum(len(item.get("failed_resources", [])) for item in storefront)
    route = sum(int(item.get("http_status") != 200 or item.get("expected_path_reached") is not True) for item in storefront)
    containment = sum(int(item.get("table_overflow_contained") is not True) for item in admin)
    checks = value["machine_checks"]
    required_checks = {"plugin-php-tests", "vsl-contract", "workflow-resume-semantics", "evidence-contract", "public-builder"}
    _require(isinstance(checks, list) and len(checks) == len(required_checks), "GATE-09 machine checks are missing or duplicated")
    observed_checks = set()
    for check in checks:
        _exact(check, {"name", "exit_code"}, "GATE-09 machine check")
        observed_checks.add(check["name"])
        _require(_integer(check["exit_code"], f"GATE-09 {check['name']} exit code") == 0, f"GATE-09 machine check failed: {check['name']}")
    _require(observed_checks == required_checks, "GATE-09 machine check inventory differs")
    log = value["php_log_window"]
    _require(isinstance(log, dict), "GATE-09 PHP log window is missing")
    _exact(log, {"started_at_utc", "finished_at_utc", "pf07_attributable_entries"}, "GATE-09 PHP log window")
    _require(isinstance(log["started_at_utc"], str) and isinstance(log["finished_at_utc"], str) and isinstance(log["pf07_attributable_entries"], list), "GATE-09 PHP log window is invalid")
    return {
        "viewport_count": len({viewport for _page, viewport in observed_pairs}),
        "storefront_page_count": len({page for page, _viewport in observed_pairs}),
        "admin_scoped_page_count": len({item.get("page") for item in admin}),
        "moderate_or_worse_violations": moderate,
        "serious_or_critical_violations": severe,
        "page_overflow_failures": overflow,
        "clipped_action_failures": clipped,
        "broken_asset_failures": broken,
        "console_error_failures": console,
        "php_fatal_warning_count": len(log["pf07_attributable_entries"]),
        "layout_overlap_failures": overlaps,
        "placeholder_or_internal_copy_failures": placeholder,
        "korean_locale_failures": locales,
        "unlabeled_control_failures": unlabeled,
        "keyboard_operability_failures": keyboard,
        "font_load_failures": fonts,
        "unresolved_skeleton_failures": skeletons,
        "visible_h1_failures": headings,
        "split_korean_word_failures": split_korean_words,
        "image_alt_failures": alt,
        "failed_resource_count": resources,
        "unexpected_http_or_route_failures": route,
        "table_containment_failures": containment,
    }


def _lease(path: Path) -> dict:
    value = _load(path)
    _root(value, "stale-lease-recovery", {"not_started", "automatic_sixth", "manual_attempt", "in_flight_cases"})
    not_started = value["not_started"]
    _exact(not_started, {"before", "after_first", "after_second", "external_call_count"}, "GATE-06 not-started recovery")
    before = not_started["before"]
    first = not_started["after_first"]
    second = not_started["after_second"]
    required_state = {"status", "attempt_count", "automatic_attempt_count", "action_count", "row_lock_count", "order_lease_count", "payload_hash"}
    for label, state in (("before", before), ("after_first", first), ("after_second", second)):
        _require(isinstance(state, dict), f"GATE-06 {label} state is missing")
        _exact(state, required_state, f"GATE-06 not-started {label}")
        _sha(state["payload_hash"], f"GATE-06 not-started {label} payload")
    counters_preserved = before["attempt_count"] == first["attempt_count"] == second["attempt_count"] and before["automatic_attempt_count"] == first["automatic_attempt_count"] == second["automatic_attempt_count"]
    requeued_once = before["status"] == "processing" and first["status"] == "retry_wait" and first["action_count"] == 1 and second == first
    locks_cleared = first["row_lock_count"] == 0 and first["order_lease_count"] == 0
    _require(_integer(not_started["external_call_count"], "GATE-06 recovery external calls") == 0, "GATE-06 recovery made an external call")
    automatic = value["automatic_sixth"]
    manual = value["manual_attempt"]
    _exact(automatic, {"status", "error_code", "attempt_count", "automatic_attempt_count", "action_count"}, "GATE-06 sixth automatic recovery")
    _exact(manual, {"status", "attempt_count", "automatic_attempt_count", "action_count"}, "GATE-06 manual recovery")
    _require(automatic == {"status": "failed", "error_code": "ATTEMPTS_EXHAUSTED", "attempt_count": 6, "automatic_attempt_count": 6, "action_count": 0}, "GATE-06 sixth-attempt recovery differs")
    _require(manual["status"] == "failed" and manual["attempt_count"] > manual["automatic_attempt_count"] and manual["action_count"] == 0, "GATE-06 manual-attempt recovery differs")
    cases = value["in_flight_cases"]
    _require(isinstance(cases, list) and {case.get("proof") for case in cases if isinstance(case, dict)} == {"CONFIRMED_NOT_POSTED", "UNPROVEN"}, "GATE-06 in-flight case set differs")
    for case in cases:
        _exact(case, {"proof", "status", "action_count", "row_lock_count", "order_lease_count", "counters_preserved", "checkpoints_preserved"}, "GATE-06 in-flight case")
        _require(case["status"] == "operator_wait" and case["action_count"] == 0 and case["row_lock_count"] == 0 and case["order_lease_count"] == 0 and case["counters_preserved"] is True and case["checkpoints_preserved"] is True, "GATE-06 in-flight recovery differs")
    return {
        "not_started_requeued_once": requeued_once,
        "counters_preserved": counters_preserved,
        "locks_cleared_exactly": locks_cleared,
        "second_sweep_mutations": int(second != first),
        "ambiguous_in_flight_state": "operator_wait",
        "ambiguous_auto_actions": sum(case["action_count"] for case in cases),
    }


def _operator(path: Path) -> dict:
    value = _load(path)
    _root(value, "operator-outcome-resolution", {"decision_records", "same_decision_replay", "conflicting_decision"})
    records = value["decision_records"]
    expected = ["CONFIRMED_POSTED", "CONFIRMED_NOT_POSTED", "RETRY_AFTER_DUE", "UNRESOLVED"]
    _require(
        isinstance(records, list)
        and len(records) == 4
        and [record.get("decision") for record in records if isinstance(record, dict)] == expected,
        "GATE-06 operator decision inventory differs",
    )
    state_keys = {
        "status", "phase", "operator_wait_epoch", "resolved_operator_wait_epoch",
        "last_operator_resolution", "action_count", "row_lock_count", "order_lease_count",
        "manual_retry_count", "checkpoint_hashes",
    }

    def state(item: object, label: str) -> dict:
        _require(isinstance(item, dict), f"{label} state is missing")
        _exact(item, state_keys, label)
        for key in ("operator_wait_epoch", "resolved_operator_wait_epoch", "action_count", "row_lock_count", "order_lease_count", "manual_retry_count"):
            _integer(item[key], f"{label} {key}")
        _require(isinstance(item["status"], str) and isinstance(item["phase"], str), f"{label} status/phase is invalid")
        _require(item["last_operator_resolution"] is None or isinstance(item["last_operator_resolution"], str), f"{label} resolution marker is invalid")
        hashes = item["checkpoint_hashes"]
        _require(isinstance(hashes, dict), f"{label} checkpoints are missing")
        _exact(hashes, {"contact", "deal", "slack"}, f"{label} checkpoints")
        for key, digest in hashes.items():
            if digest is not None:
                _sha(digest, f"{label} {key} checkpoint")
        return item

    indexed: dict[str, dict] = {}
    for record in records:
        _exact(
            record,
            {"decision", "before", "result", "after", "resolution_external_calls", "pre_resolution_slack_posts", "post_resolution"},
            "GATE-06 operator decision record",
        )
        decision = record["decision"]
        before = state(record["before"], f"GATE-06 {decision} before")
        after = state(record["after"], f"GATE-06 {decision} after")
        _require(
            before["status"] == "operator_wait"
            and before["operator_wait_epoch"] >= 1
            and before["resolved_operator_wait_epoch"] < before["operator_wait_epoch"]
            and before["action_count"] == 0
            and before["row_lock_count"] == 0
            and before["order_lease_count"] == 0,
            f"GATE-06 {decision} did not begin at an unresolved fenced operator wait",
        )
        result = record["result"]
        _require(isinstance(result, dict), f"GATE-06 {decision} result is missing")
        _exact(result, {"status", "action_id_present", "idempotent"}, f"GATE-06 {decision} result")
        _require(isinstance(result["status"], str) and isinstance(result["action_id_present"], bool) and result["idempotent"] is False, f"GATE-06 {decision} result is invalid")
        _require(_integer(record["resolution_external_calls"], f"GATE-06 {decision} resolution calls") == 0, f"GATE-06 {decision} resolution made an external call")
        _integer(record["pre_resolution_slack_posts"], f"GATE-06 {decision} prior Slack posts")
        indexed[decision] = record

    posted = indexed["CONFIRMED_POSTED"]
    posted_before = posted["before"]
    posted_after = posted["after"]
    _require(
        posted["result"] == {"status": "completed", "action_id_present": False, "idempotent": False}
        and posted["pre_resolution_slack_posts"] == 1
        and posted["post_resolution"] is None
        and posted_after["status"] == "completed"
        and posted_after["phase"] == "completed"
        and posted_after["action_count"] == 0
        and posted_after["resolved_operator_wait_epoch"] == posted_before["operator_wait_epoch"]
        and posted_after["last_operator_resolution"] == "CONFIRMED_POSTED"
        and all(posted_after["checkpoint_hashes"][key] is not None for key in ("contact", "deal", "slack")),
        "GATE-06 CONFIRMED_POSTED transition differs",
    )

    for decision, expected_status in (("CONFIRMED_NOT_POSTED", "pending"), ("RETRY_AFTER_DUE", "retry_wait")):
        record = indexed[decision]
        before = record["before"]
        after = record["after"]
        post = record["post_resolution"]
        _require(isinstance(post, dict), f"GATE-06 {decision} resume evidence is missing")
        _exact(post, {"premature_runner_mutations", "n8n_execution_count", "slack_post_count", "final"}, f"GATE-06 {decision} resume")
        final = state(post["final"], f"GATE-06 {decision} final")
        _require(
            record["result"] == {"status": expected_status, "action_id_present": True, "idempotent": False}
            and record["pre_resolution_slack_posts"] == 0
            and after["status"] == expected_status
            and after["phase"] == "created"
            and after["action_count"] == 1
            and after["manual_retry_count"] == before["manual_retry_count"] + 1
            and after["resolved_operator_wait_epoch"] == before["operator_wait_epoch"]
            and after["last_operator_resolution"] == decision
            and _integer(post["premature_runner_mutations"], f"GATE-06 {decision} premature mutations") == 0
            and _integer(post["n8n_execution_count"], f"GATE-06 {decision} executions") == 1
            and _integer(post["slack_post_count"], f"GATE-06 {decision} Slack posts") == 1
            and final["status"] == "completed"
            and final["phase"] == "completed"
            and final["action_count"] == 0
            and final["checkpoint_hashes"]["slack"] is not None,
            f"GATE-06 {decision} resume transition differs",
        )

    unresolved_record = indexed["UNRESOLVED"]
    unresolved_before = unresolved_record["before"]
    unresolved = unresolved_record["after"]
    _require(
        unresolved_record["result"] == {"status": "operator_wait", "action_id_present": False, "idempotent": False}
        and unresolved_record["pre_resolution_slack_posts"] == 0
        and unresolved_record["post_resolution"] is None
        and unresolved["status"] == "operator_wait"
        and unresolved["action_count"] == 0
        and unresolved["resolved_operator_wait_epoch"] == unresolved_before["resolved_operator_wait_epoch"]
        and unresolved["last_operator_resolution"] == "UNRESOLVED",
        "GATE-06 UNRESOLVED transition differs",
    )
    replay = value["same_decision_replay"]
    _exact(replay, {"outcome", "new_action_count", "external_call_count"}, "GATE-06 same-decision replay")
    conflict = value["conflicting_decision"]
    _exact(conflict, {"outcome", "external_call_count", "action_count"}, "GATE-06 conflicting decision")
    _require(replay["outcome"] == "idempotent_noop" and replay["new_action_count"] == 0 and replay["external_call_count"] == 0, "GATE-06 same-decision replay is not idempotent")
    _require(conflict["outcome"] == "conflict" and conflict["external_call_count"] == 0 and conflict["action_count"] == 0, "GATE-06 conflicting decision had a side effect")
    proven = indexed["CONFIRMED_NOT_POSTED"]
    return {
        "decision_count": len(records),
        "decisions": [record["decision"] for record in records],
        "proven_not_posted_resume_actions": _integer(proven["after"]["action_count"], "GATE-06 proven resume actions"),
        "proven_resume_total_slack_posts": _integer(proven["post_resolution"]["slack_post_count"], "GATE-06 proven resume Slack posts"),
        "unresolved_state": unresolved["status"],
        "unresolved_actions": _integer(unresolved["action_count"], "GATE-06 unresolved actions"),
        "same_decision_replay": replay["outcome"],
        "conflicting_decision_side_effects": _integer(conflict["external_call_count"], "GATE-06 conflict side effects"),
    }


def _restore(path: Path) -> dict:
    value = _load(path)
    _root(value, "clean-restore", {
        "https", "backup", "quiescence", "compose", "run_identity", "order_selection", "reprovision",
        "credential_smokes", "order_flow", "remote_observations", "duplicate_replay", "runtime",
    })

    https = value["https"]
    _exact(https, {"mode", "scheme", "tls_verified", "observed_status", "response_body_sha256"}, "GATE-10 HTTPS")
    _require(
        https["mode"] == "ON_DEMAND_HTTPS_TUNNEL"
        and https["scheme"] == "https"
        and https["tls_verified"] is True
        and _integer(https["observed_status"], "GATE-10 HTTPS status") == 200,
        "GATE-10 HTTPS staging observation differs",
    )
    _sha(https["response_body_sha256"], "GATE-10 HTTPS response body")

    backup = value["backup"]
    _exact(backup, {"manifest_exit_code", "failed_entry_count", "manifest_sha256", "artifact_kinds", "artifact_count", "nonempty_artifact_count"}, "GATE-10 backup")
    _sha(backup["manifest_sha256"], "GATE-10 backup manifest")
    artifact_kinds = backup["artifact_kinds"]
    required_artifact_kinds = {
        "n8n_reference_volume",
        "plugin_source_and_configuration",
        "protected_locator_inventory",
        "runtime_configuration",
        "selected_n8n_workflow",
        "wordpress_application_volume",
        "wordpress_database",
        "wordpress_uploads",
    }
    _require(
        isinstance(artifact_kinds, list)
        and len(artifact_kinds) == len(set(artifact_kinds))
        and set(artifact_kinds) == required_artifact_kinds,
        "GATE-10 formal backup artifact inventory differs",
    )
    artifact_count = _integer(backup["artifact_count"], "GATE-10 backup artifact count")
    nonempty_artifact_count = _integer(backup["nonempty_artifact_count"], "GATE-10 nonempty backup artifact count")
    _require(
        _integer(backup["manifest_exit_code"], "GATE-10 manifest exit") == 0
        and _integer(backup["failed_entry_count"], "GATE-10 manifest failures") == 0
        and artifact_count == len(required_artifact_kinds)
        and nonempty_artifact_count == artifact_count,
        "GATE-10 formal backup is incomplete or unverified",
    )

    quiescence = value["quiescence"]
    _exact(quiescence, {"wordpress_before_stop", "n8n_before_stop", "original_after_stop"}, "GATE-10 quiescence")
    wordpress_quiet = quiescence["wordpress_before_stop"]
    _exact(wordpress_quiet, {"pending_pf07_actions", "running_pf07_actions", "processing_pf07_rows", "active_pf07_leases"}, "GATE-10 WordPress quiescence")
    n8n_quiet = quiescence["n8n_before_stop"]
    _exact(n8n_quiet, {"running_executions", "waiting_executions"}, "GATE-10 n8n quiescence")
    stopped = quiescence["original_after_stop"]
    _exact(stopped, {"queue_runner_running", "webhook_running", "all_compose_services_stopped"}, "GATE-10 original stop")
    original_quiescent = all(
        _integer(observed, f"GATE-10 quiescence {name}") == 0
        for name, observed in {**wordpress_quiet, **n8n_quiet}.items()
    )
    _require(
        original_quiescent
        and stopped == {"queue_runner_running": False, "webhook_running": False, "all_compose_services_stopped": True},
        "GATE-10 original runtime was not drained and stopped",
    )

    compose = value["compose"]
    _exact(compose, {"clean_project", "project_sha256", "original_project_sha256", "preexisting_resource_count", "volumes", "services"}, "GATE-10 Compose")
    project_sha = _sha(compose["project_sha256"], "GATE-10 restored Compose project")
    original_project_sha = _sha(compose["original_project_sha256"], "GATE-10 original Compose project")
    _require(
        compose["clean_project"] is True
        and project_sha != original_project_sha
        and _integer(compose["preexisting_resource_count"], "GATE-10 preexisting resource count") == 0,
        "GATE-10 Compose project is not clean and distinct",
    )
    volumes = compose["volumes"]
    _exact(volumes, {"database", "wordpress", "n8n"}, "GATE-10 volume inventory")
    for name, volume in volumes.items():
        _exact(volume, {"name_sha256", "original_name_sha256", "created_for_project"}, f"GATE-10 {name} volume")
        _require(
            _sha(volume["name_sha256"], f"GATE-10 {name} volume name")
            != _sha(volume["original_name_sha256"], f"GATE-10 original {name} volume name")
            and volume["created_for_project"] is True,
            f"GATE-10 {name} volume was reused",
        )
    services = compose["services"]
    _exact(services, {"database", "wordpress", "n8n", "task_runners", "edge"}, "GATE-10 restored services")
    _require(all(state == "running" for state in services.values()), "GATE-10 restored service set is not running")

    identity = value["run_identity"]
    _exact(identity, {"shop_instance_sha256", "original_shop_instance_sha256", "restore_run_sha256", "pre_restore_run_sha256", "remote_order_key_sha256"}, "GATE-10 run identity")
    _require(
        _sha(identity["shop_instance_sha256"], "GATE-10 restored shop")
        == _sha(identity["original_shop_instance_sha256"], "GATE-10 original shop"),
        "GATE-10 SHOP_INSTANCE_ID was not preserved",
    )
    restore_run_sha = _sha(identity["restore_run_sha256"], "GATE-10 restore run")
    _sha(identity["remote_order_key_sha256"], "GATE-10 remote order key")
    pre = identity["pre_restore_run_sha256"]
    _require(isinstance(pre, list) and bool(pre) and all(_sha(item, "GATE-10 pre-restore run") for item in pre), "GATE-10 pre-restore run inventory differs")
    _require(len(pre) == len(set(pre)) and restore_run_sha not in pre, "GATE-10 RESTORE_RUN_ID is not distinct")

    selection = value["order_selection"]
    _exact(selection, {
        "bounded_candidate_limit", "preexisting_remote_collision_count",
        "discarded_unprocessed_candidate_count", "selected_remote_deal_count_before",
    }, "GATE-10 restored order selection")
    candidate_limit = _integer(selection["bounded_candidate_limit"], "GATE-10 candidate limit", 1)
    collision_count = _integer(selection["preexisting_remote_collision_count"], "GATE-10 remote collision count")
    discarded_count = _integer(selection["discarded_unprocessed_candidate_count"], "GATE-10 discarded candidate count")
    selected_deals_before = _integer(selection["selected_remote_deal_count_before"], "GATE-10 selected preexisting Deal count")
    _require(
        candidate_limit == 20
        and collision_count < candidate_limit
        and discarded_count == collision_count
        and selected_deals_before == 0,
        "GATE-10 restored order selection did not establish an unused bounded candidate",
    )

    reprovision = value["reprovision"]
    _exact(reprovision, {"mode", "outbound_enabled_during_restore", "owner_setup_exit_code", "workflow_import_exit_code", "workflow_publish_exit_code", "imported_credential_count", "credential_binding_count", "workflow_active"}, "GATE-10 reprovision")
    reprovisioned = (
        reprovision["mode"] == "REPROVISIONED_RESTORE"
        and reprovision["outbound_enabled_during_restore"] is False
        and _integer(reprovision["owner_setup_exit_code"], "GATE-10 owner setup exit") == 0
        and _integer(reprovision["workflow_import_exit_code"], "GATE-10 workflow import exit") == 0
        and _integer(reprovision["workflow_publish_exit_code"], "GATE-10 workflow publish exit") == 0
        and _integer(reprovision["imported_credential_count"], "GATE-10 imported credentials") == 2
        and _integer(reprovision["credential_binding_count"], "GATE-10 credential bindings") == 2
        and reprovision["workflow_active"] is True
    )
    _require(reprovisioned, "GATE-10 workflow or credential reprovision differs")

    smoke = value["credential_smokes"]
    _exact(smoke, {"hubspot", "slack"}, "GATE-10 credential smoke")
    hubspot_smoke = smoke["hubspot"]
    slack_smoke = smoke["slack"]
    _exact(hubspot_smoke, {"status", "http_status", "pipeline_match_count"}, "GATE-10 HubSpot credential smoke")
    _exact(slack_smoke, {"status", "http_status", "auth_ok"}, "GATE-10 Slack credential smoke")
    _require(
        hubspot_smoke["status"] == "PASS"
        and _integer(hubspot_smoke["http_status"], "GATE-10 HubSpot smoke status") == 200
        and _integer(hubspot_smoke["pipeline_match_count"], "GATE-10 HubSpot pipeline matches") == 1
        and slack_smoke["status"] == "PASS"
        and _integer(slack_smoke["http_status"], "GATE-10 Slack smoke status") == 200
        and slack_smoke["auth_ok"] is True,
        "GATE-10 recreated credential smoke failed",
    )

    flow = value["order_flow"]
    _exact(flow, {"created", "payment"}, "GATE-10 order flow")
    for name, event in flow.items():
        _exact(event, {"row_status", "action_id_present", "n8n_execution_delta", "execution_status", "event_key_sha256", "payload_sha256", "hubspot_outbound_call_count", "slack_outbound_call_count", "returned_slack_timestamp_present"}, f"GATE-10 {name} event")
        _sha(event["event_key_sha256"], f"GATE-10 {name} event key")
        _sha(event["payload_sha256"], f"GATE-10 {name} payload")
        _require(
            event["row_status"] == "completed"
            and event["action_id_present"] is False
            and _integer(event["n8n_execution_delta"], f"GATE-10 {name} n8n executions") == 1
            and event["execution_status"] == "success"
            and _integer(event["hubspot_outbound_call_count"], f"GATE-10 {name} HubSpot calls", 1) >= 1,
            f"GATE-10 {name} event did not complete through restored n8n and HubSpot",
        )
    _require(
        _integer(flow["created"]["slack_outbound_call_count"], "GATE-10 created Slack calls") == 0
        and flow["created"]["returned_slack_timestamp_present"] is False
        and _integer(flow["payment"]["slack_outbound_call_count"], "GATE-10 payment Slack calls") == 1
        and flow["payment"]["returned_slack_timestamp_present"] is True,
        "GATE-10 Slack event routing differs",
    )

    remote = value["remote_observations"]
    _exact(remote, {"deal_before", "deal_after", "deal_id_sha256", "order_key_sha256", "original_calls_before", "original_calls_after"}, "GATE-10 remote observations")
    _sha(remote["deal_id_sha256"], "GATE-10 restored Deal")
    _require(
        _sha(remote["order_key_sha256"], "GATE-10 observed order key") == identity["remote_order_key_sha256"],
        "GATE-10 remote readback order key differs",
    )

    duplicate = value["duplicate_replay"]
    _exact(duplicate, {"same_outbox_row", "event_key_sha256_before", "event_key_sha256_after", "payload_sha256_before", "payload_sha256_after", "attempt_count_before", "attempt_count_after", "action_id_present_before", "action_id_present_after", "n8n_execution_before", "n8n_execution_after", "slack_calls_before", "slack_calls_after", "deal_count_before", "deal_count_after"}, "GATE-10 duplicate replay")
    duplicate_noop = (
        duplicate["same_outbox_row"] is True
        and _sha(duplicate["event_key_sha256_before"], "GATE-10 duplicate event before")
        == _sha(duplicate["event_key_sha256_after"], "GATE-10 duplicate event after")
        and _sha(duplicate["payload_sha256_before"], "GATE-10 duplicate payload before")
        == _sha(duplicate["payload_sha256_after"], "GATE-10 duplicate payload after")
        and _integer(duplicate["attempt_count_before"], "GATE-10 duplicate attempt before")
        == _integer(duplicate["attempt_count_after"], "GATE-10 duplicate attempt after")
        and duplicate["action_id_present_before"] is False
        and duplicate["action_id_present_after"] is False
        and _integer(duplicate["n8n_execution_before"], "GATE-10 duplicate n8n before")
        == _integer(duplicate["n8n_execution_after"], "GATE-10 duplicate n8n after")
        and _integer(duplicate["slack_calls_before"], "GATE-10 duplicate Slack before")
        == _integer(duplicate["slack_calls_after"], "GATE-10 duplicate Slack after")
        and _integer(duplicate["deal_count_before"], "GATE-10 duplicate Deal before") == 1
        and _integer(duplicate["deal_count_after"], "GATE-10 duplicate Deal after") == 1
    )
    _require(duplicate_noop, "GATE-10 duplicate payment replay was not a no-op")

    runtime = value["runtime"]
    _exact(runtime, {"active_after_restore", "restored_queue_enabled", "restored_webhook_active", "original_outbound_enabled", "original_all_services_stopped"}, "GATE-10 runtime")
    _require(
        runtime == {
            "active_after_restore": "RESTORED",
            "restored_queue_enabled": True,
            "restored_webhook_active": True,
            "original_outbound_enabled": False,
            "original_all_services_stopped": True,
        },
        "GATE-10 active runtime designation differs",
    )

    deal_delta = _integer(remote["deal_after"], "GATE-10 Deal after") - _integer(remote["deal_before"], "GATE-10 Deal before")
    original_calls = _integer(remote["original_calls_after"], "GATE-10 original calls after") - _integer(remote["original_calls_before"], "GATE-10 original calls before")
    payment_slack = _integer(flow["payment"]["slack_outbound_call_count"], "GATE-10 payment Slack posts")
    duplicate_slack = _integer(duplicate["slack_calls_after"], "GATE-10 duplicate Slack after") - _integer(duplicate["slack_calls_before"], "GATE-10 duplicate Slack before")
    return {
        "https_mode": https["mode"],
        "clean_compose_project": True,
        "fresh_wordpress_database_and_volume": True,
        "fresh_n8n_runtime_and_volume": True,
        "backup_artifact_count": artifact_count,
        "original_quiescent_before_snapshot": original_quiescent,
        "reprovisioned_workflow_credential_bindings": reprovisioned,
        "restored_hubspot_credential_smoke": hubspot_smoke["status"],
        "restored_slack_credential_smoke": slack_smoke["status"],
        "new_order_created_and_paid": True,
        "restored_created_n8n_executions": flow["created"]["n8n_execution_delta"],
        "restored_payment_n8n_executions": flow["payment"]["n8n_execution_delta"],
        "new_deal_count": deal_delta,
        "payment_slack_posts": payment_slack,
        "duplicate_additional_slack_posts": duplicate_slack,
        "duplicate_n8n_executions": duplicate["n8n_execution_after"] - duplicate["n8n_execution_before"],
        "original_runtime_calls": original_calls,
        "active_runtime_after_restore": runtime["active_after_restore"],
        "original_outbound_runtime_enabled": runtime["original_outbound_enabled"],
        "restored_webhook_and_queue_enabled": runtime["restored_queue_enabled"] and runtime["restored_webhook_active"],
        "original_services_stopped": runtime["original_all_services_stopped"],
        "formal_backup_manifest_verified": True,
    }


DERIVERS: dict[str, tuple[str, Callable[[Path], dict]]] = {
    "normal-order": ("gate01_order_variety_trace", _normal_order),
    "variable-input": ("gate03_variable_input_trace", _variable_input),
    "state-non-regression": ("gate02_state_trace", _state_non_regression),
    "concurrent-duplicate-suppression": ("gate04_duplicate_trace", _duplicate),
    "hmac-rejection": ("gate05_hmac_trace", _hmac),
    "raw-byte-resource-bounds": ("gate05_resource_trace", _resource),
    "stale-lease-recovery": ("gate06_lease_trace", _lease),
    "operator-outcome-resolution": ("gate06_operator_trace", _operator),
    "reconciliation-repair": ("gate08_reconciliation_trace", _reconciliation),
    "hpos-compatibility": ("gate09_compatibility_trace", _compatibility),
    "product-quality": ("gate09_product_quality_trace", _product_quality),
    "clean-restore": ("gate10_restore_trace", _restore),
}


def derive_fixture_observations(fixture_id: str, artifact_paths: dict[str, Path]) -> dict | None:
    selected = DERIVERS.get(fixture_id)
    if selected is None:
        return None
    alias, derive = selected
    _require(set(artifact_paths) == {alias}, f"{fixture_id} semantic artifact set differs")
    return derive(artifact_paths[alias])
