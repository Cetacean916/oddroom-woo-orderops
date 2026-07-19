#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from acceptance_semantics import AcceptanceSemanticError, derive_fixture_observations


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def payload(order_id: int, email: str, sku: str) -> dict:
    raw = json.dumps({
        "order": {
            "id": order_id,
            "customer": {"email": email},
            "items": [{"sku": sku, "quantity": 1}],
        },
    }, ensure_ascii=False, separators=(",", ":"))
    return {"payload_json": raw, "stored_payload_hash": hashlib.sha256(raw.encode()).hexdigest()}


def write(directory: Path, name: str, value: dict) -> Path:
    path = directory / name
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def derive(directory: Path, fixture_id: str, alias: str, value: dict) -> dict:
    result = derive_fixture_observations(fixture_id, {alias: write(directory, f"{fixture_id}.json", value)})
    require(isinstance(result, dict), f"{fixture_id} did not derive observations")
    return result


with tempfile.TemporaryDirectory(prefix="pf07-semantic-test-") as temporary:
    directory = Path(temporary)

    normal_orders = [
        {"order_id": 1, "product_id": 11, "variation_id": 0, "shape": "simple", "coupon_applied": False, "payload": payload(1, "a@example.com", "A")},
        {"order_id": 2, "product_id": 12, "variation_id": 22, "shape": "variable", "coupon_applied": False, "payload": payload(2, "b@example.com", "B")},
        {"order_id": 3, "product_id": 13, "variation_id": 0, "shape": "coupon", "coupon_applied": True, "payload": payload(3, "c@example.com", "C")},
    ]
    normal = {"schema_version": 1, "fixture_id": "normal-order", "orders": normal_orders, "admin_order_ids": [1, 2, 3], "storage_order_ids": [1, 2, 3]}
    observed = derive(directory, "normal-order", "gate01_order_variety_trace", normal)
    require(observed["immutable_payload_hashes_valid"] is True and observed["coupon_orders"] == 1, "GATE-01 derivation differs")
    corrupted = copy.deepcopy(normal)
    corrupted["orders"][0]["payload"]["stored_payload_hash"] = "0" * 64
    try:
        derive(directory, "normal-order", "gate01_order_variety_trace", corrupted)
    except AcceptanceSemanticError:
        pass
    else:
        raise SystemExit("FAIL: GATE-01 accepted a changed payload commitment")

    variable_orders = []
    for index, order in enumerate(normal_orders, start=101):
        item = copy.deepcopy(order)
        item = {
            "order_id": item["order_id"],
            "execution_id": index,
            "verified_payload_sha256": item["payload"]["stored_payload_hash"],
            "payload": item["payload"],
        }
        variable_orders.append(item)
    variable = {"schema_version": 1, "fixture_id": "variable-input", "orders": variable_orders}
    observed = derive(directory, "variable-input", "gate03_variable_input_trace", variable)
    require(observed["fixed_workflow_fixture_used"] is False and observed["distinct_payload_hash_count"] == 3, "GATE-03 derivation differs")

    event_types = [("ORDER_CREATED", 10), ("PAYMENT_CONFIRMED", 20), ("ORDER_CANCELLED", 30), ("ORDER_REFUNDED", 40)]
    state = {
        "schema_version": 1,
        "fixture_id": "state-non-regression",
        "events": [
            {"event_type": event_type, "state_rank": rank, "payload": payload(rank, f"{rank}@example.com", event_type), "execution_result": "completed"}
            for event_type, rank in event_types
        ],
        "concurrent_claim": {"worker_invocations": 2, "row_claim_owners": 1, "order_lease_owners": 1, "adapter_dispatches": 1},
        "delayed_lower_rank": [
            {"event_type": event_type, "result": "stale_ignored", "slack_calls": 0, "rank_before": 40, "rank_after": 40, "pipeline_before": "closedwon", "pipeline_after": "closedwon"}
            for event_type in ("ORDER_CREATED", "PAYMENT_CONFIRMED")
        ],
        "authoritative_readback": {"state_rank": 40, "pipeline": "closedwon"},
    }
    observed = derive(directory, "state-non-regression", "gate02_state_trace", state)
    require(observed["event_state_ranks"] == [10, 20, 30, 40] and observed["delayed_payment_slack_calls"] == 0, "GATE-02 derivation differs")

    duplicate = {
        "schema_version": 1,
        "fixture_id": "concurrent-duplicate-suppression",
        "worker_invocations": [
            {"invocation_id": index, "row_claim_owned": index == 1, "order_lease_owned": index == 1, "adapter_dispatched": index == 1}
            for index in (1, 2, 3)
        ],
        "immutable_rows": [{"outbox_id": 10, "payload": payload(10, "dup@example.com", "DUP")}],
        "manual_retry": {"attempted_during_claim": True, "outcome": "conflict", "lock_token_sha256_before": "a" * 64, "lock_token_sha256_after": "a" * 64},
        "n8n_executions": [{"execution_id": 99, "status": "success", "slack_outbound_call_count": 1, "returned_slack_timestamp_present": True}],
        "hubspot_readback": {"deal_count": 1},
    }
    observed = derive(directory, "concurrent-duplicate-suppression", "gate04_duplicate_trace", duplicate)
    require(observed["concurrent_workers"] == 3 and observed["row_claim_owners"] == 1, "GATE-04 derivation differs")

    rejected = [
        {"name": name, "http_status": 401, "executed_nodes": ["Signed Raw Webhook", "Reject Before Side Effects"], "hubspot_calls": 0, "association_calls": 0, "slack_calls": 0, "deal_count": 0}
        for name in ("missing_signature", "mutated_body", "expired_timestamp")
    ]
    valid_bytes = {"http_status": 200, "body_sha256": "b" * 64, "authenticated_body_sha256": "b" * 64, "non_ascii_present": True, "insignificant_whitespace_present": True}
    hmac = {"schema_version": 1, "fixture_id": "hmac-rejection", "rejected_cases": rejected, "valid_exact_bytes": valid_bytes}
    observed = derive(directory, "hmac-rejection", "gate05_hmac_trace", hmac)
    require(observed["rejected_case_count"] == 3 and observed["external_call_count"] == 0, "GATE-05 HMAC derivation differs")

    resource = {
        "schema_version": 1,
        "fixture_id": "raw-byte-resource-bounds",
        "maximum_body_bytes": 262144,
        "oversized": {"sent_bytes": 262145, "http_status": 413, "n8n_execution_before": 7, "n8n_execution_after": 7, "hubspot_calls_before": 2, "hubspot_calls_after": 2, "association_calls_before": 1, "association_calls_after": 1, "slack_calls_before": 1, "slack_calls_after": 1},
        "resource_invalid": {"http_status": 400, "executed_nodes": ["Reject Before Side Effects"], "hubspot_calls": 0, "association_calls": 0, "slack_calls": 0, "deal_count": 0},
        "valid_exact_bytes": {**valid_bytes, "reserialized_old_signature_status": 401},
    }
    observed = derive(directory, "raw-byte-resource-bounds", "gate05_resource_trace", resource)
    require(observed["oversized_status"] == 413 and observed["oversized_workflow_execution_delta"] == 0, "GATE-05 resource derivation differs")

    not_started_state = {"status": "processing", "attempt_count": 1, "automatic_attempt_count": 1, "action_count": 0, "row_lock_count": 1, "order_lease_count": 1, "payload_hash": "c" * 64}
    recovered_state = {**not_started_state, "status": "retry_wait", "action_count": 1, "row_lock_count": 0, "order_lease_count": 0}
    lease = {
        "schema_version": 1,
        "fixture_id": "stale-lease-recovery",
        "not_started": {"before": not_started_state, "after_first": recovered_state, "after_second": recovered_state, "external_call_count": 0},
        "automatic_sixth": {"status": "failed", "error_code": "ATTEMPTS_EXHAUSTED", "attempt_count": 6, "automatic_attempt_count": 6, "action_count": 0},
        "manual_attempt": {"status": "failed", "attempt_count": 7, "automatic_attempt_count": 6, "action_count": 0},
        "in_flight_cases": [
            {"proof": proof, "status": "operator_wait", "action_count": 0, "row_lock_count": 0, "order_lease_count": 0, "counters_preserved": True, "checkpoints_preserved": True}
            for proof in ("CONFIRMED_NOT_POSTED", "UNPROVEN")
        ],
    }
    observed = derive(directory, "stale-lease-recovery", "gate06_lease_trace", lease)
    require(observed["not_started_requeued_once"] is True and observed["ambiguous_auto_actions"] == 0, "GATE-06 lease derivation differs")

    def operator_state(status: str, phase: str, epoch: int, resolved: int, resolution: str | None, actions: int, manual: int, checkpoints: bool = False) -> dict:
        return {
            "status": status,
            "phase": phase,
            "operator_wait_epoch": epoch,
            "resolved_operator_wait_epoch": resolved,
            "last_operator_resolution": resolution,
            "action_count": actions,
            "row_lock_count": 0,
            "order_lease_count": 0,
            "manual_retry_count": manual,
            "checkpoint_hashes": {
                "contact": "d" * 64 if checkpoints else None,
                "deal": "e" * 64 if checkpoints else None,
                "slack": "f" * 64 if checkpoints else None,
            },
        }

    decisions = ["CONFIRMED_POSTED", "CONFIRMED_NOT_POSTED", "RETRY_AFTER_DUE", "UNRESOLVED"]
    decision_records = []
    for epoch, decision in enumerate(decisions, start=1):
        before = operator_state("operator_wait", "created", epoch, 0, None, 0, 0)
        if decision == "CONFIRMED_POSTED":
            result = {"status": "completed", "action_id_present": False, "idempotent": False}
            after = operator_state("completed", "completed", epoch, epoch, decision, 0, 0, True)
            prior_slack = 1
            post = None
        elif decision in {"CONFIRMED_NOT_POSTED", "RETRY_AFTER_DUE"}:
            status = "pending" if decision == "CONFIRMED_NOT_POSTED" else "retry_wait"
            result = {"status": status, "action_id_present": True, "idempotent": False}
            after = operator_state(status, "created", epoch, epoch, decision, 1, 1)
            prior_slack = 0
            post = {
                "premature_runner_mutations": 0,
                "n8n_execution_count": 1,
                "slack_post_count": 1,
                "final": operator_state("completed", "completed", epoch, epoch, decision, 0, 1, True),
            }
        else:
            result = {"status": "operator_wait", "action_id_present": False, "idempotent": False}
            after = operator_state("operator_wait", "created", epoch, 0, "UNRESOLVED", 0, 0)
            prior_slack = 0
            post = None
        decision_records.append({
            "decision": decision,
            "before": before,
            "result": result,
            "after": after,
            "resolution_external_calls": 0,
            "pre_resolution_slack_posts": prior_slack,
            "post_resolution": post,
        })
    operator = {
        "schema_version": 1,
        "fixture_id": "operator-outcome-resolution",
        "decision_records": decision_records,
        "same_decision_replay": {"outcome": "idempotent_noop", "new_action_count": 0, "external_call_count": 0},
        "conflicting_decision": {"outcome": "conflict", "external_call_count": 0, "action_count": 0},
    }
    observed = derive(directory, "operator-outcome-resolution", "gate06_operator_trace", operator)
    require(observed["decision_count"] == 4 and observed["conflicting_decision_side_effects"] == 0, "GATE-06 operator derivation differs")

    sources = {"ORDER_CREATED": "date_created", "PAYMENT_CONFIRMED": "date_paid", "ORDER_CANCELLED": "_oddroom_orderops_cancelled_at_utc", "ORDER_REFUNDED": "full_refund_completion"}
    repairs = []
    for index, (event_type, source) in enumerate(sources.items(), start=1):
        snapshot = {"row_count": 1, "action_count": 1, "payload": payload(index, f"r{index}@example.com", event_type)}
        repairs.append({"event_type": event_type, "fact_source": source, "before_row_count": 0, "after_first": snapshot, "after_second": snapshot})
    schedule_payload = payload(20, "schedule@example.com", "SCHEDULE")
    reconciliation = {
        "schema_version": 1,
        "fixture_id": "reconciliation-repair",
        "repairs": repairs,
        "schedule_repair": {
            "before": {"row_count": 1, "action_count": 0, "payload": schedule_payload},
            "after_first": {"row_count": 1, "action_count": 1, "payload": schedule_payload},
            "after_second": {"row_count": 1, "action_count": 1, "payload": schedule_payload},
        },
    }
    observed = derive(directory, "reconciliation-repair", "gate08_reconciliation_trace", reconciliation)
    require(observed["missing_event_repairs"] == 4 and observed["second_scan_mutations"] == 0, "GATE-08 derivation differs")

    check_names = ["hpos_disabled", "hpos_enabled", "activation_dependency_rejection", "migration_idempotence", "uninstall_preserve_default", "uninstall_opt_in_removal", "scheduler_failure_branches"]
    compatibility = {
        "schema_version": 1,
        "fixture_id": "hpos-compatibility",
        "environment": {"wordpress": "6.8.2", "woocommerce": "10.0.2", "php": "8.3.0", "action_scheduler_version": "4.0.0", "action_scheduler_source": "woocommerce", "tables_transactional": True, "database_utc": "2026-07-19T00:00:00.000000Z"},
        "checks": [],
    }
    compatibility_details = {
        "hpos_disabled": {"hpos_enabled": False, "outbox_row_present": True, "payload_hash_valid": True, "wc_order_readable": True},
        "hpos_enabled": {"hpos_enabled": True, "outbox_row_present": True, "payload_hash_valid": True, "wc_order_readable": True},
        "activation_dependency_rejection": {"activation_without_woocommerce_exit": 1, "plugin_active_after_rejection": False, "pf07_table_count_after_rejection": 0, "activation_after_woocommerce_exit": 0},
        "migration_idempotence": {"starting_schema_option": "1.0.0", "starting_table_count": 2, "ending_schema_option": "1.1.0", "ending_table_count": 3, "tables_innodb": True, "repeated_schema_unchanged": True},
        "uninstall_preserve_default": {"tables_before": 3, "rows_before": 2, "tables_after": 3, "rows_after": 2, "data_preserved": True},
        "uninstall_opt_in_removal": {"candidate_actions_before": 2, "candidate_actions_after": 0, "tables_after": 0, "schema_option_after": None},
        "scheduler_failure_branches": {
            "unsupported_version": {"returned_action_id": 0, "status": "pending", "action_id": None, "attempt_count": 0, "lease_count": 0, "error_code": "ACTION_SCHEDULER_VERSION_UNSUPPORTED", "candidate_count": 0},
            "stale_preflight": {"returned_action_id": 0, "status": "pending", "action_id": None, "attempt_count": 0, "lease_count": 0, "error_code": "ACTION_SCHEDULER_PREFLIGHT_REQUIRED", "candidate_count": 0},
            "supported_preflight": {"status": "PASS", "version": "4.0.0", "source": "woocommerce", "row_101_candidate_count": 1, "row_102_candidate_count": 1, "duplicate_raw_id": 0, "remaining_candidate_count": 0},
            "isolated_branch_assertions": 23,
            "isolated_branch_failures": 0,
        },
    }
    compatibility["checks"] = [
        {"name": name, "exit_code": 0, "assertion_count": 1, "failure_count": 0, "details": compatibility_details[name]}
        for name in check_names
    ]
    observed = derive(directory, "hpos-compatibility", "gate09_compatibility_trace", compatibility)
    require(observed["hpos_enabled"] == "PASS" and observed["action_scheduler_version_supported"] is True, "GATE-09 compatibility derivation differs")

    storefront = []
    for viewport in (390, 768, 1440):
        for page in ("home", "shop", "product", "cart", "checkout", "account"):
            storefront.append({
                "page": page,
                "viewport_width": viewport,
                "url_alias": f"PF07_{page.upper()}",
                "mode": "full_document",
                "http_status": 200,
                "expected_path_reached": True,
                "critical_or_serious": [],
                "page_overflow_px": 0,
                "horizontally_clipped_control_count": 0,
                "broken_image_count": 0,
                "image_without_alt_count": 0,
                "placeholder_asset_count": 0,
                "console_errors": [],
                "failed_resources": [],
                "korean_locale": True,
                "forbidden_copy": False,
                "overlapping_control_count": 0,
                "unlabeled_control_count": 0,
                "keyboard_inoperable_control_count": 0,
                "required_font_load_failures": 0,
                "unresolved_skeleton_count": 0,
            })
    admin = [{
        "page": "admin",
        "viewport_width": viewport,
        "url_alias": "PF07_ADMIN",
        "mode": "scoped",
        "root_selector": ".oddroom-orderops",
        "http_status": 200,
        "critical_or_serious": [],
        "console_errors": [],
        "table_overflow_contained": True,
        "horizontally_clipped_action_count": 0,
        "overlapping_protected_action_count": 0,
        "unlabeled_protected_action_count": 0,
    } for viewport in (390, 768, 1440)]
    product = {
        "schema_version": 1,
        "fixture_id": "product-quality",
        "ui_evidence": {"storefront": storefront, "admin": admin, "failures": []},
        "machine_checks": [{"name": name, "exit_code": 0} for name in ("plugin-php-tests", "vsl-contract", "workflow-resume-semantics", "evidence-contract", "public-builder")],
        "php_log_window": {"started_at_utc": "2026-07-19T00:00:00Z", "finished_at_utc": "2026-07-19T00:01:00Z", "pf07_attributable_entries": []},
    }
    observed = derive(directory, "product-quality", "gate09_product_quality_trace", product)
    require(
        observed["viewport_count"] == 3
        and observed["console_error_failures"] == 0
        and observed["placeholder_or_internal_copy_failures"] == 0
        and observed["layout_overlap_failures"] == 0
        and observed["korean_locale_failures"] == 0,
        "GATE-09 product derivation differs",
    )

    restore = {
        "schema_version": 1,
        "fixture_id": "clean-restore",
        "https": {"mode": "ON_DEMAND_HTTPS_TUNNEL", "scheme": "https", "tls_verified": True, "observed_status": 200, "response_body_sha256": "a" * 64},
        "backup": {
            "manifest_exit_code": 0,
            "failed_entry_count": 0,
            "manifest_sha256": "b" * 64,
            "artifact_kinds": [
                "n8n_reference_volume",
                "plugin_source_and_configuration",
                "protected_locator_inventory",
                "runtime_configuration",
                "selected_n8n_workflow",
                "wordpress_application_volume",
                "wordpress_database",
                "wordpress_uploads",
            ],
            "artifact_count": 8,
            "nonempty_artifact_count": 8,
        },
        "quiescence": {
            "wordpress_before_stop": {"pending_pf07_actions": 0, "running_pf07_actions": 0, "processing_pf07_rows": 0, "active_pf07_leases": 0},
            "n8n_before_stop": {"running_executions": 0, "waiting_executions": 0},
            "original_after_stop": {"queue_runner_running": False, "webhook_running": False, "all_compose_services_stopped": True},
        },
        "compose": {
            "clean_project": True,
            "project_sha256": "c" * 64,
            "original_project_sha256": "d" * 64,
            "preexisting_resource_count": 0,
            "volumes": {
                "database": {"name_sha256": "e" * 64, "original_name_sha256": "f" * 64, "created_for_project": True},
                "wordpress": {"name_sha256": "1" * 64, "original_name_sha256": "2" * 64, "created_for_project": True},
                "n8n": {"name_sha256": "3" * 64, "original_name_sha256": "4" * 64, "created_for_project": True},
            },
            "services": {"database": "running", "wordpress": "running", "n8n": "running", "task_runners": "running", "edge": "running"},
        },
        "run_identity": {
            "shop_instance_sha256": "5" * 64,
            "original_shop_instance_sha256": "5" * 64,
            "restore_run_sha256": "6" * 64,
            "pre_restore_run_sha256": ["7" * 64],
            "remote_order_key_sha256": "8" * 64,
        },
        "order_selection": {
            "bounded_candidate_limit": 20,
            "preexisting_remote_collision_count": 1,
            "discarded_unprocessed_candidate_count": 1,
            "selected_remote_deal_count_before": 0,
        },
        "reprovision": {
            "mode": "REPROVISIONED_RESTORE",
            "outbound_enabled_during_restore": False,
            "owner_setup_exit_code": 0,
            "workflow_import_exit_code": 0,
            "workflow_publish_exit_code": 0,
            "imported_credential_count": 2,
            "credential_binding_count": 2,
            "workflow_active": True,
        },
        "credential_smokes": {
            "hubspot": {"status": "PASS", "http_status": 200, "pipeline_match_count": 1},
            "slack": {"status": "PASS", "http_status": 200, "auth_ok": True},
        },
        "order_flow": {
            "created": {"row_status": "completed", "action_id_present": False, "n8n_execution_delta": 1, "execution_status": "success", "event_key_sha256": "9" * 64, "payload_sha256": "a" * 64, "hubspot_outbound_call_count": 4, "slack_outbound_call_count": 0, "returned_slack_timestamp_present": False},
            "payment": {"row_status": "completed", "action_id_present": False, "n8n_execution_delta": 1, "execution_status": "success", "event_key_sha256": "b" * 64, "payload_sha256": "c" * 64, "hubspot_outbound_call_count": 3, "slack_outbound_call_count": 1, "returned_slack_timestamp_present": True},
        },
        "remote_observations": {"deal_before": 0, "deal_after": 1, "deal_id_sha256": "d" * 64, "order_key_sha256": "8" * 64, "original_calls_before": 9, "original_calls_after": 9},
        "duplicate_replay": {
            "same_outbox_row": True,
            "event_key_sha256_before": "b" * 64,
            "event_key_sha256_after": "b" * 64,
            "payload_sha256_before": "c" * 64,
            "payload_sha256_after": "c" * 64,
            "attempt_count_before": 1,
            "attempt_count_after": 1,
            "action_id_present_before": False,
            "action_id_present_after": False,
            "n8n_execution_before": 12,
            "n8n_execution_after": 12,
            "slack_calls_before": 4,
            "slack_calls_after": 4,
            "deal_count_before": 1,
            "deal_count_after": 1,
        },
        "runtime": {"active_after_restore": "RESTORED", "restored_queue_enabled": True, "restored_webhook_active": True, "original_outbound_enabled": False, "original_all_services_stopped": True},
    }
    observed = derive(directory, "clean-restore", "gate10_restore_trace", restore)
    require(
        observed["new_deal_count"] == 1
        and observed["formal_backup_manifest_verified"] is True
        and observed["backup_artifact_count"] == 8
        and observed["duplicate_n8n_executions"] == 0,
        "GATE-10 derivation differs",
    )
    replayed = copy.deepcopy(restore)
    replayed["duplicate_replay"]["n8n_execution_after"] += 1
    try:
        derive(directory, "clean-restore", "gate10_restore_trace", replayed)
    except AcceptanceSemanticError:
        pass
    else:
        raise SystemExit("FAIL: GATE-10 accepted a duplicate replay with a new n8n execution")
    invalid_selection = copy.deepcopy(restore)
    invalid_selection["order_selection"]["selected_remote_deal_count_before"] = 1
    try:
        derive(directory, "clean-restore", "gate10_restore_trace", invalid_selection)
    except AcceptanceSemanticError:
        pass
    else:
        raise SystemExit("FAIL: GATE-10 accepted a selected order key with a preexisting Deal")

print("PASS: acceptance evidence semantics are derived from executable-artifact observations")
