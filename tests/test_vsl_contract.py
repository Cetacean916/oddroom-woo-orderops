#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = json.loads((ROOT / "workflow/oddroom-orderops-vsl.json").read_text(encoding="utf-8"))
PAYLOAD_SCHEMA = json.loads((ROOT / "workflow/payload-schema-v1.json").read_text(encoding="utf-8"))
COMPOSE = (ROOT / "infra/compose.yaml").read_text(encoding="utf-8")
TASK_RUNNER_DOCKERFILE = (ROOT / "infra/task-runner.Dockerfile").read_text(encoding="utf-8")
TASK_RUNNER_CONFIG = (ROOT / "infra/n8n-task-runners.json").read_text(encoding="utf-8")
TASK_RUNNER_LOCK = (ROOT / "infra/task-runner-deps/package-lock.json").read_text(encoding="utf-8")
NGINX = (ROOT / "infra/nginx.conf").read_text(encoding="utf-8")
PLUGIN = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted((ROOT / "plugin/oddroom-orderops").rglob("*.php"))
)
ADMIN = (ROOT / "plugin/oddroom-orderops/includes/class-oddroom-admin.php").read_text(encoding="utf-8")
SCHEDULER = (ROOT / "plugin/oddroom-orderops/includes/class-oddroom-scheduler.php").read_text(encoding="utf-8")
WORKER = (ROOT / "plugin/oddroom-orderops/includes/class-oddroom-worker.php").read_text(encoding="utf-8")
FAULTS = (ROOT / "plugin/oddroom-orderops/includes/class-oddroom-faults.php").read_text(encoding="utf-8")
CLI = (ROOT / "plugin/oddroom-orderops/includes/class-oddroom-cli.php").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "plugin/oddroom-orderops/oddroom-orderops.php").read_text(encoding="utf-8")
DEPENDENCIES = (ROOT / "plugin/oddroom-orderops/includes/class-oddroom-dependencies.php").read_text(encoding="utf-8")
STOREFRONT = (ROOT / "plugin/oddroom-orderops/includes/class-oddroom-storefront.php").read_text(encoding="utf-8")
PRIVATE_ADMIN = (ROOT / "plugin/oddroom-orderops/includes/class-oddroom-private-admin.php").read_text(encoding="utf-8")
STOREFRONT_CSS = (ROOT / "plugin/oddroom-orderops/assets/css/storefront.css").read_text(encoding="utf-8")
EVENTS = (ROOT / "plugin/oddroom-orderops/includes/class-oddroom-events.php").read_text(encoding="utf-8")
RECONCILIATION = (ROOT / "plugin/oddroom-orderops/includes/class-oddroom-reconciliation.php").read_text(encoding="utf-8")
REPOSITORY = (ROOT / "plugin/oddroom-orderops/includes/class-oddroom-repository.php").read_text(encoding="utf-8")
UNINSTALL = (ROOT / "plugin/oddroom-orderops/uninstall.php").read_text(encoding="utf-8")
QUEUE_RUNNER = (ROOT / "scripts/queue-runner").read_text(encoding="utf-8")
RUNTIME_WP_INSTALL = (ROOT / "scripts/runtime-wp-install").read_text(encoding="utf-8")
GATE06_PROBE = (ROOT / "scripts/probe-gate06").read_text(encoding="utf-8")
GATE06_LEASE_PROBE = (ROOT / "scripts/probe-gate06-lease").read_text(encoding="utf-8")
GATE06_OPERATOR_PROBE = (ROOT / "scripts/probe-gate06-operator").read_text(encoding="utf-8")
CORE_ACCEPTANCE_PROBE = (ROOT / "scripts/probe-core-acceptance").read_text(encoding="utf-8")
GATE09_COMPATIBILITY_PROBE = (ROOT / "scripts/probe-gate09-compatibility").read_text(encoding="utf-8")
GATE09_PRODUCT_PROBE = (ROOT / "scripts/probe-gate09-product-quality").read_text(encoding="utf-8")
GATE10_RESTORE_PROBE = (ROOT / "scripts/probe-clean-restore").read_text(encoding="utf-8")
FIXTURE_MANIFEST = json.loads((ROOT / "fixtures/acceptance-fixtures.json").read_text(encoding="utf-8"))
FIXTURE_RUNNER = (ROOT / "fixtures/run").read_text(encoding="utf-8")
ACCEPTANCE_SEMANTICS = (ROOT / "scripts/acceptance_semantics.py").read_text(encoding="utf-8")
EVIDENCE_COLLECTOR = (ROOT / "scripts/collect-evidence").read_text(encoding="utf-8")
MEDIA_RECORDER = (ROOT / "scripts/record-public-media.mjs").read_text(encoding="utf-8")
STILL_BUILDER = (ROOT / "scripts/build-public-stills.mjs").read_text(encoding="utf-8")
PUBLIC_VALIDATOR = (ROOT / "scripts/validate-public").read_text(encoding="utf-8")
CI_SCRIPT = (ROOT / "scripts/ci").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def walk_schema(value: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(walk_schema(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(walk_schema(child))
    return found


require(PAYLOAD_SCHEMA.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "payload schema is not versioned Draft 2020-12 JSON Schema")
require(PAYLOAD_SCHEMA.get("$id") == "urn:oddroom-orderops:payload-schema:1",
        "payload schema identity changed")
for schema_node in walk_schema(PAYLOAD_SCHEMA):
    node_type = schema_node.get("type")
    if node_type == "object":
        require(schema_node.get("additionalProperties") is False,
                "an object schema permits additional properties")
        properties = schema_node.get("properties")
        required = schema_node.get("required")
        require(isinstance(properties, dict) and isinstance(required, list)
                and set(properties) == set(required),
                "an object schema does not require its exact declared property set")
    elif node_type == "array":
        require(all(key in schema_node for key in ("minItems", "maxItems", "items")),
                "an array schema lacks explicit item bounds")
    elif node_type == "string":
        require(any(key in schema_node for key in ("const", "enum", "format", "pattern", "minLength", "maxLength")),
                "a string schema lacks an explicit resource or format constraint")
require(PAYLOAD_SCHEMA["$defs"]["order"]["properties"]["items"]["maxItems"] == 100
        and PAYLOAD_SCHEMA["$defs"]["order"]["properties"]["coupon_codes"]["maxItems"] == 50,
        "payload schema array bounds changed")
require(PAYLOAD_SCHEMA["$defs"]["signed64NonNegative"]["maximum"] == 9223372036854775807,
        "payload schema signed-64 bound changed")
require(PAYLOAD_SCHEMA["$defs"]["order"]["properties"]["id"]["minimum"] == 0,
        "payload schema rejects the contracted non-negative order-ID boundary")
require(PAYLOAD_SCHEMA["$defs"]["item"]["properties"]["sku"]["minLength"] == 0,
        "payload schema rejects a valid empty WooCommerce SKU")


nodes = WORKFLOW["nodes"]
webhooks = [node for node in nodes if node["type"] == "n8n-nodes-base.webhook"]
require(len(webhooks) == 1, "exactly one production webhook is required")
require(webhooks[0]["parameters"]["options"].get("rawBody") is True, "raw body is not enabled")
require(webhooks[0]["parameters"].get("responseMode") == "responseNode", "response node is not explicit")

http_nodes = [node for node in nodes if node["type"] == "n8n-nodes-base.httpRequest"]
urls = [node["parameters"]["url"] for node in http_nodes]
require(urls == [
    "https://api.hubapi.com/crm/objects/2026-03/deals/batch/read",
    "https://api.hubapi.com/crm/objects/2026-03/contacts/batch/upsert",
    "https://api.hubapi.com/crm/objects/2026-03/contacts/batch/read",
    "https://api.hubapi.com/crm/objects/2026-03/deals/batch/upsert",
    "https://api.hubapi.com/crm/objects/2026-03/deals/batch/read",
    "={{ $json.association_put_url }}",
    "={{ $json.association_read_url }}",
    "http://wordpress/wp-json/oddroom-orderops/v1/fault-before-slack",
    "https://slack.com/api/chat.postMessage",
], "HubSpot transport is not the fixed 2026-03 complete CRM path")
require([node["parameters"]["method"] for node in http_nodes] == [
    "POST", "POST", "POST", "POST", "POST", "PUT", "GET", "POST", "POST",
], "complete outbound-path methods changed")
hubspot_nodes = [node for node in http_nodes if node["name"].startswith("HubSpot 2026-03")]
slack_nodes = [node for node in http_nodes if node["name"] == "Slack chat.postMessage"]
fault_lookup_nodes = [node for node in http_nodes if node["name"] == "Lookup Active Pre-Post Fault"]
require(len(hubspot_nodes) == 7, "HubSpot complete-path call set changed")
require(len(slack_nodes) == 1, "Slack path must contain exactly one outbound post node")
require(len(fault_lookup_nodes) == 1, "signed pre-post fault lookup changed")
for node in hubspot_nodes:
    require(node["parameters"].get("authentication") == "genericCredentialType", "HTTP auth is not credential-backed")
    require(node["parameters"].get("genericAuthType") == "httpBearerAuth", "HTTP auth type changed")
    credential = node.get("credentials", {}).get("httpBearerAuth", {})
    require(set(credential) == {"id", "name"}, "workflow contains non-reference credential material")
slack_credential = slack_nodes[0].get("credentials", {}).get("httpHeaderAuth", {})
require(slack_nodes[0]["parameters"].get("genericAuthType") == "httpHeaderAuth", "Slack auth type changed")
require(set(slack_credential) == {"id", "name"}, "Slack workflow contains non-reference credential material")
require("X-OddRoom-Fault-Signature" in json.dumps(fault_lookup_nodes[0]), "fault lookup is not signed")

code = "\n".join(node["parameters"].get("jsCode", "") for node in nodes)
for required in (
    "item.binary?.data?.data",
    "Buffer.from(rawBase64, 'base64')",
    "crypto.timingSafeEqual",
    "$env.ODDROOM_WEBHOOK_HMAC_KEY",
    "['created','deal_resolved','contact_upserted','deal_upserted','associated','slack_pending']",
    "idProperty: 'email'",
    "firstname: order.customer.first_name",
    "/associations/default/deal/",
    "$env.SLACK_CHANNEL_ID",
    "SLACK_RETRYABLE_BEFORE_POST",
    "SLACK_OUTCOME_UNKNOWN",
    "contact_mutation_required",
    "deal_mutation_required",
    "association_mutation_required",
    "A Slack-producing created replay is ambiguous.",
    "result: 'duplicate_noop'",
    "require('json-bigint')",
    "require('bignumber.js')",
    "Array.from(value).length",
    "new BigNumber('9223372036854775807')",
    "Buffer.from(rawText, 'utf8').equals(raw)",
    "const selectedCurrency = 'KRW'",
    "const selectedCurrencyPrecision = 2",
    "order.currency === selectedCurrency",
    "const exactKeys = (value, keys)",
    "const utcSecond = (value)",
    "exactKeys(payload, ['schema_version','event_key','shop_instance_id','run_id','event_type','occurred_at_utc','occurred_at_source','state_rank','order'])",
    "bounded(value.sku, 0, 255)",
    "signed64(order.id, true)",
    "const presentationExact = properties.dealname ===",
    "const associationPending = body?.status === 'PENDING'",
    "Staging pre-post authorization could not be established.",
    "const retryNumber = /^[0-9]+$/.test(retryText)",
):
    require(required in code, f"workflow invariant missing: {required}")
require("HUBSPOT_RUNTIME_TOKEN" not in code, "runtime token alias entered workflow code")
require(not re.search(r"Bearer\\s+[A-Za-z0-9._-]{12,}", code), "Bearer credential entered workflow")
require("return stop(200, envelope('stale_ignored'" in code and "mode = 'stale'" not in code,
        "a lower-rank event does not stop immediately after authoritative Deal resolution")

connections = WORKFLOW["connections"]
require(connections["Contact Mutation Required"]["main"][0][0]["node"] == "HubSpot 2026-03 Contact Upsert"
        and connections["Contact Mutation Required"]["main"][1][0]["node"] == "HubSpot 2026-03 Contact Read",
        "Contact resume branch does not separate mutation from read-only verification")
require(connections["Deal Mutation Required"]["main"][0][0]["node"] == "HubSpot 2026-03 Deal Upsert"
        and connections["Deal Mutation Required"]["main"][1][0]["node"] == "HubSpot 2026-03 Deal Readback",
        "Deal resume branch does not separate mutation from read-only verification")
require(connections["Association Mutation Required"]["main"][0][0]["node"] == "HubSpot 2026-03 Default Association"
        and connections["Association Mutation Required"]["main"][1][0]["node"] == "HubSpot 2026-03 Association Read",
        "Association resume branch does not separate mutation from read-only verification")

for digest in (
    "wordpress@sha256:", "mariadb@sha256:", "docker.n8n.io/n8nio/n8n@sha256:",
    "nginx@sha256:",
):
    require(digest in COMPOSE, f"container digest is not pinned: {digest}")
require("n8nio/runners@sha256:d890fe221de44d75e1900eaf83f4499ad63503bfcc97cb04f0abfe5bc48bc0a6"
        in TASK_RUNNER_DOCKERFILE, "task-runner base image digest changed")
require("node@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd"
        in TASK_RUNNER_DOCKERFILE, "task-runner dependency builder digest changed")
require("oddroom-orderops-task-runners:2.25.7-json-bigint-1.0.0" in COMPOSE,
        "custom exact-integer task-runner image changed")
require('"NODE_FUNCTION_ALLOW_EXTERNAL": "json-bigint,bignumber.js"' in TASK_RUNNER_CONFIG,
        "exact-integer parser modules are not the explicit Code-node external allowlist")
require('"NODE_FUNCTION_ALLOW_BUILTIN": "crypto"' in TASK_RUNNER_CONFIG,
        "Code-node HMAC builtin is not explicitly allowed")
require('"json-bigint": "1.0.0"' in TASK_RUNNER_LOCK
        and '"bignumber.js": "9.3.1"' in TASK_RUNNER_LOCK,
        "exact task-runner parser dependencies are not lockfile-pinned")
require('"127.0.0.1:${PF07_WORDPRESS_PORT:-18081}:80"' in COMPOSE, "WordPress is not loopback-bound")
require('"127.0.0.1:${PF07_N8N_PORT:-15678}:5678"' in COMPOSE, "n8n editor is not loopback-bound")
require('"127.0.0.1:${PF07_PUBLIC_PORT:-18080}:8080"' in COMPOSE, "public ingress is not loopback-bound")
require("client_max_body_size 256k;" in NGINX, "ingress raw-body cap changed")
require("location = /webhook/oddroom-orderops-v1" in NGINX, "production webhook route changed")
require("wp-admin" in NGINX and "wp-login" in NGINX and "return 404;" in NGINX, "WordPress administration is exposed by ingress")
require("resolver 127.0.0.11 valid=10s ipv6=off;" in NGINX
        and "proxy_pass $n8n_upstream;" in NGINX
        and "proxy_pass $wordpress_upstream;" in NGINX,
        "edge upstream DNS remains pinned to a container address across service recreation")
require("SLACK_CHANNEL_ID" in COMPOSE, "Slack destination fact is not runtime-bound")
owner_home_paths = set(re.findall("/" + r"home/[^/<\s]+(?:/[^<\s]*)?", COMPOSE))
require(owner_home_paths == {"/" + "home/node/.n8n"}, "compose contains a non-canonical owner-home path")
require("OddRoom_Dependencies::assertActivationReady();" in PLUGIN,
        "plugin activation does not enforce the dependency gate")
require("$booted || !OddRoom_Dependencies::runtimeReady()" in BOOTSTRAP,
        "plugin runtime bootstrap does not stop on dependency failure")
require("add_action('action_scheduler_init', $oddroomOrderOpsBoot, 20);" in BOOTSTRAP
        and "add_action('init', $oddroomOrderOpsBoot, 20);" in BOOTSTRAP,
        "plugin bootstrap is not bound to initialized Action Scheduler with an init fallback")
require(BOOTSTRAP.index("OddRoom_Dependencies::runtimeReady()") < BOOTSTRAP.index("OddRoom_Scheduler::boot()")
        and BOOTSTRAP.index("OddRoom_Dependencies::runtimeReady()") < BOOTSTRAP.index("OddRoom_Events::boot()")
        and BOOTSTRAP.index("OddRoom_Dependencies::runtimeReady()") < BOOTSTRAP.index("OddRoom_Reconciliation::boot()"),
        "external-effect modules boot before the dependency gate")
for dependency_code in (
    "WOOCOMMERCE_UNAVAILABLE", "ACTION_SCHEDULER_NOT_READY", "ACTION_SCHEDULER_VERSION_UNSUPPORTED",
    "WOOCOMMERCE_CURRENCY_MISMATCH", "WOOCOMMERCE_CURRENCY_PRECISION_MISMATCH",
):
    require(dependency_code in DEPENDENCIES, f"dependency failure code is absent: {dependency_code}")
require("No order automation was started." in DEPENDENCIES
        and "add_action('admin_notices'" in DEPENDENCIES,
        "dependency failure lacks an actionable administrator notice")
require("public const SELECTED_CURRENCY = 'KRW';" in PLUGIN
        and "public const SELECTED_CURRENCY_PRECISION = 2;" in PLUGIN,
        "selected WooCommerce currency and precision are not code-pinned")
require("option update woocommerce_currency KRW" in RUNTIME_WP_INSTALL
        and "option update woocommerce_price_num_decimals 2" in RUNTIME_WP_INSTALL,
        "runtime installer does not pin selected WooCommerce currency precision")
require("language core install ko_KR --activate" in RUNTIME_WP_INSTALL
        and "language plugin install woocommerce ko_KR" in RUNTIME_WP_INSTALL
        and "oddroom-orderops setup-storefront" in RUNTIME_WP_INSTALL,
        "runtime installer does not deliver the Korean-first storefront")

for column in (
    "event_key", "payload_json", "payload_hash", "attempt_count", "automatic_attempt_count",
    "action_id", "adapter_dispatch_state", "adapter_dispatch_attempt", "lock_token",
    "remote_deal_id", "operator_wait_epoch",
):
    require(column in PLUGIN, f"outbox contract field is absent: {column}")
require("ENGINE=InnoDB" in PLUGIN, "transactional table engine is not explicit")
require("oddroom_orderops_fault_controls" in PLUGIN, "transactional fault-control table is absent")
require("expires_at>UTC_TIMESTAMP(6)" in PLUGIN, "database-clock fault expiry authorization is absent")
require("INTERVAL %d MINUTE" in PLUGIN and "$minutes > 30" in PLUGIN, "fault expiry is not bounded to 30 minutes")
require("public const GROUP = 'oddroom-orderops'" in PLUGIN, "scheduler group changed")
require("[$rowId]" in PLUGIN, "canonical positional integer argument path is absent")
require("deferContentionRequeue" in PLUGIN, "order-lease contention does not defer a replacement action")
require("schedulingSuppressed" in SCHEDULER
        and "OddRoom_Faults::SUPPRESS_SCHEDULE" in SCHEDULER
        and "self::schedulingSuppressed($row)" in SCHEDULER
        and "self::scheduleEligibleRow($row);" in SCHEDULER,
        "global eligible-row repair bypasses the active schedule-suppression fixture")
require("unlinkFinishedEligibleAction" in PLUGIN, "completed eligible actions cannot be unlinked atomically")
require("$transitionedAt = (string) $wpdb->get_var('SELECT UTC_TIMESTAMP(6)')" in REPOSITORY
        and "'SELECT DATE_ADD(%s, INTERVAL %d SECOND)'" in REPOSITORY
        and "lock_expires_at = NULL, updated_at = %s" in REPOSITORY,
        "retry due time and updated_at do not share one database-clock anchor")
link_action_source = REPOSITORY.split("public static function linkAction", 1)[1].split(
    "public static function unlinkFinishedEligibleAction", 1
)[0]
require("updated_at" not in link_action_source,
        "Action Scheduler ID linking overwrites the retry transition time anchor")
require("register_shutdown_function" in PLUGIN, "contention requeue runs before Action Scheduler completes the old action")
require("linkedEligibleRows" in SCHEDULER and "unlinkFinishedEligibleAction" in SCHEDULER,
        "finished pending/retry action links cannot be repaired")
require(re.search(
    r"as_schedule_single_action\(\s*\$timestamp,\s*self::HOOK,\s*\[\$rowId\],\s*self::GROUP,\s*true\s*\)",
    SCHEDULER,
) is not None, "business scheduling does not use Action Scheduler uniqueness")
require(re.search(r"self::GROUP,\s*false\s*\)", SCHEDULER) is None,
        "a PF07 scheduler path bypasses Action Scheduler uniqueness")
require("action_scheduler_completed_action" in SCHEDULER
        and "handleCompletedBusinessAction" in SCHEDULER
        and "self::scheduleEligibleRow($row" in SCHEDULER,
        "eligible follow-up is not scheduled after the finishing action becomes complete")
require("OddRoom_Scheduler::scheduleFollowup(" not in WORKER
        and "OddRoom_Scheduler::scheduleBusiness(" not in WORKER,
        "worker schedules a follow-up before Action Scheduler marks the current action complete")
require("$stored !== null && $stored !== $returned" in PLUGIN,
        "write-once checkpoints permit deletion")
require("throw new RuntimeException('LOCK_LOST')" in PLUGIN,
        "checkpoint-conflict fencing failure is silently accepted")
claim_code = REPOSITORY.split("public static function claim", 1)[1].split("public static function markDispatched", 1)[0]
require("DELETE FROM {$leases}" not in claim_code,
        "row claim can delete an expired order lease without the fenced recovery path")
require("$httpStatus !== 200" in WORKER and "$httpStatus !== 409" in WORKER
        and "$httpStatus < 500" in WORKER,
        "authenticated adapter result is not mapped to its normative HTTP status")
require("terminalResponseFailure" in WORKER and "$httpStatus !== 429" in WORKER,
        "terminal 4xx and retryable 429 response failures are not separated")
require("['slack_posted', 'completed']" in WORKER and "ADAPTER_RESPONSE_INVALID" in WORKER,
        "a post-terminal phase can issue another adapter request")
require("oddroom-orderops reset-checkout-limit" in CLI
        and "SYNTHETIC_CHECKOUT_RATE_LIMIT_ONLY" in CLI
        and "ON_DEMAND_ONLY" in CLI,
        "protected synthetic checkout recording setup is missing or unbounded")
require("UPDATE {$wpdb->options}" in STOREFRONT
        and "CAST(option_value AS UNSIGNED) < %d" in STOREFRONT
        and "INSERT IGNORE INTO {$wpdb->options}" in STOREFRONT
        and "oddroom_checkout_v2_" in STOREFRONT,
        "checkout rate limit is not an atomic database counter")
require("oddroom_checkout_synthetic_identity_required" in STOREFRONT
        and "isSyntheticIdentity" in STOREFRONT
        and "@example\\.com" in STOREFRONT,
        "classic and Store API checkout do not enforce synthetic identities")
for hook in (
    "woocommerce_payment_complete",
    "woocommerce_order_status_cancelled",
    "woocommerce_order_refunded",
):
    require(hook in PLUGIN, f"WooCommerce event hook is absent: {hook}")
for event_type, rank in (
    ("ORDER_CREATED", 10),
    ("PAYMENT_CONFIRMED", 20),
    ("ORDER_CANCELLED", 30),
    ("ORDER_REFUNDED", 40),
):
    require(f"'{event_type}' => {rank}" in PLUGIN, f"event rank is absent: {event_type}")
require("_oddroom_orderops_cancelled_at_utc" in PLUGIN, "protected cancellation fact is absent")
require("get_total_refunded" in PLUGIN and "full_refund_completion" in PLUGIN, "full-refund fact path is absent")
for fixture in ("simple", "variable", "coupon"):
    require(f"'{fixture}'" in PLUGIN, f"acceptance fixture is absent: {fixture}")
require("WC_Product_Variation" in PLUGIN, "variable-product fixture is absent")
require("WC_Coupon" in PLUGIN and "apply_coupon" in PLUGIN, "coupon fixture is absent")
require("ambiguousSlackFailure" in PLUGIN and "SLACK_OUTCOME_UNKNOWN" in PLUGIN, "ambiguous Slack response path is absent")
require("'Error code', 'Sanitized error'" in ADMIN, "admin does not separate stable and sanitized errors")
require("$row->error_code ?? '—'" in ADMIN and "$row->last_error ?? '—'" in ADMIN, "admin omits an error field")
require("echo '<td>' . esc_html((string) $value) . '</td>';" in ADMIN, "admin row values are not escaped")
require("current_user_can('manage_woocommerce')" in ADMIN, "admin action capability guard is absent")
require("check_admin_referer($nonceAction)" in ADMIN, "action-specific nonce guard is absent")
for decision in ("CONFIRMED_POSTED", "CONFIRMED_NOT_POSTED", "RETRY_AFTER_DUE", "UNRESOLVED"):
    require(decision in PLUGIN, f"Resolve Outcome decision is absent: {decision}")
require("DEFAULT_WINDOW_DAYS = 7" in PLUGIN and "PAGE_SIZE = 50" in PLUGIN, "reconciliation bounds changed")
require("wc_get_orders" in PLUGIN and "fullRefundCompletion" in PLUGIN, "fact-derived reconciliation is absent")
require("oddroom_orderops_reconcile_hourly" in PLUGIN, "hourly reconciliation hook is absent")
require("ON_DEMAND_ONLY" in PLUGIN and "blog_public" in PLUGIN, "storefront control mode or noindex setup is absent")
require("pre_wp_mail" in PLUGIN and "woocommerce_available_payment_gateways" in PLUGIN, "synthetic checkout containment is absent")
require("Product proof surface" not in STOREFRONT and "Synthetic catalog" not in STOREFRONT
        and "OddRoom 드롭 키트" in STOREFRONT and "OddRoom 캠페인 팩" in STOREFRONT
        and "$product->set_slug('oddroom-drop-kit')" in STOREFRONT
        and "$product->set_category_ids([$categoryId])" in STOREFRONT,
        "buyer storefront still exposes validation copy or lacks stable product identity")
require('.oddroom-hero h1' in STOREFRONT_CSS
        and 'font-family: "OddRoom Sans", system-ui, sans-serif;' in STOREFRONT_CSS
        and '--odd-border: 2px solid var(--odd-ink);' in STOREFRONT_CSS,
        "buyer storefront typography or restrained design token is absent")
require("normalizeMoney((string) $item->get_total())" in REPOSITORY
        and "normalizeMoney((string) $order->get_total())" in REPOSITORY
        and "toMinorUnits" in EVENTS and "toMinorUnits" in RECONCILIATION
        and "addMinorUnits" in RECONCILIATION,
        "money or full-refund facts are not exact decimal-string operations")
require("(float)" not in EVENTS and "(float)" not in RECONCILIATION and "(float)" not in REPOSITORY,
        "a business money or refund decision still narrows through binary float")
require("parseUtcTimestamp($stored)" in EVENTS and "parseUtcTimestamp($cancelledRaw)" in RECONCILIATION,
        "protected cancellation facts do not use strict calendar validation")
require("assertPhaseCheckpointConsistency" in WORKER,
        "adapter response phases are not checked against returned checkpoints")
require("invalidResponseDisposition" in WORKER
        and "if ($requiresSlack && $httpStatus !== 429)" in WORKER,
        "a malformed Slack-event response can bypass outcome-unknown handling")
require("DEFAULT_TEST_PAUSE_SECONDS = 120" in WORKER
        and "ODDROOM_TEST_PAUSE_SECONDS" in WORKER
        and "integer from 1 through 120" in WORKER
        and "sleep(self::testPauseSeconds())" in WORKER,
        "staging concurrency probes cannot select a bounded worker hold interval")
require("GATE04_CLAIM_HOLD_SECONDS = 45" in CORE_ACCEPTANCE_PROBE
        and '"ODDROOM_TEST_PAUSE_SECONDS": str(GATE04_CLAIM_HOLD_SECONDS)' in CORE_ACCEPTANCE_PROBE,
        "GATE-04 does not retain the live claim long enough for rival workers and Manual Retry")
require("PAUSE_AFTER_RESPONSE" in FAULTS
        and "pauseForCrashFixture($claimed, OddRoom_Faults::PAUSE_AFTER_RESPONSE)" in WORKER,
        "staging response-loss probes cannot stop after an observed adapter response")
require("LEASE_SECONDS = 600" in REPOSITORY
        and "ODDROOM_TEST_LEASE_SECONDS" in REPOSITORY
        and "integer from 1 through 600" in REPOSITORY
        and REPOSITORY.count("$leaseSeconds = self::leaseSeconds();") == 2,
        "staging crash-recovery probes cannot select a bounded database lease")
require("A no-op result cannot establish a new Slack post." in WORKER
        and "A stale short-circuit cannot establish a Contact checkpoint." in WORKER,
        "stale or duplicate no-op response invariants permit new checkpoints or Slack state")
require("oddroom_checkout_v2_" in UNINSTALL,
        "opt-in uninstall leaves dynamic synthetic checkout counters behind")
require("PF07_QUEUE_WEBHOOK_URL_OVERRIDE" in QUEUE_RUNNER
        and "private-container PF07 webhook URL" in QUEUE_RUNNER
        and 'wpcli_environment=(-e "ODDROOM_WEBHOOK_URL=$webhook_override")' in QUEUE_RUNNER,
        "foreground queue runner cannot use the bounded acceptance fault route")
require("self::startHtmlRewrite();" in PRIVATE_ADMIN
        and "private static bool $htmlRewriteStarted" in PRIVATE_ADMIN
        and "$protocolRelative = $canonicalAuthority === '' ? '' : '//' . $canonicalAuthority;" in PRIVATE_ADMIN
        and "$escapedProtocolRelative = str_replace('/', '\\\\/', $protocolRelative);" in PRIVATE_ADMIN
        and "$privateProtocolRelative = '//' . $privateAuthority;" in PRIVATE_ADMIN
        and "$escapedPrivateProtocolRelative = str_replace('/', '\\\\/', $privateProtocolRelative);" in PRIVATE_ADMIN
        and "$protocolRelative === '' ? '' : $privateProtocolRelative" in PRIVATE_ADMIN
        and "$escapedProtocolRelative === '' ? '' : $escapedPrivateProtocolRelative" in PRIVATE_ADMIN
        and "add_action('wp_loaded', [self::class, 'startHtmlRewrite']" not in PRIVATE_ADMIN,
        "loopback administrator HTML rewriting starts too late for WordPress core asset URLs")
require("pressSequentially(value, { delay: 42 })" in MEDIA_RECORDER
        and "runVisibleOperation" in MEDIA_RECORDER
        and "visible_terminal_foreground_queue_exit_zero" in MEDIA_RECORDER
        and "visible_terminal_stop_n8n_exit_zero" in MEDIA_RECORDER
        and "visible_terminal_start_n8n_exit_zero" in MEDIA_RECORDER
        and "visible_terminal_failure_worker_exit_zero" in MEDIA_RECORDER
        and "visible_terminal_recovery_worker_exit_zero" in MEDIA_RECORDER
        and '"$PF07_VISIBLE_QUEUE_RUNNER" --once' in MEDIA_RECORDER
        and 'docker compose --env-file "$PF07_VISIBLE_RUNTIME_ENV"' in MEDIA_RECORDER
        and "actual_checkout_observed: true" in MEDIA_RECORDER
        and "visible_worker_terminal_observed: true" in MEDIA_RECORDER,
        "public media recorder can regress to narrated static screens instead of visible real execution")
require("source_event_frame_sha256" in STILL_BUILDER
        and "sha256(result.stdout) !== event.frame_sha256" in STILL_BUILDER
        and "LIVE_STOREFRONT" in STILL_BUILDER
        and "PRODUCT_SELECTED" in STILL_BUILDER
        and "CHECKOUT_INPUT" in STILL_BUILDER,
        "public storefront still can regress to an unbound or placeholder composition")
require('sys.dont_write_bytecode = True' in PUBLIC_VALIDATOR
        and 'os.environ["PYTHONDONTWRITEBYTECODE"] = "1"' in PUBLIC_VALIDATOR
        and "public candidate contains files outside the generated exact inventory" in PUBLIC_VALIDATOR
        and "public validation mutated the generated exact inventory" in PUBLIC_VALIDATOR,
        "public validation can mutate or accept files outside the exact release inventory")
require(CI_SCRIPT.index("./scripts/validate-public --pre-public")
        < CI_SCRIPT.index("npm ci --prefix infra/task-runner-deps"),
        "CI can generate dependency files before exact public-tree validation")
require("export PYTHONDONTWRITEBYTECODE=1" in CI_SCRIPT,
        "CI Python checks can leave bytecode outside the exact public inventory")
require("run_queue_once()" in GATE06_PROBE
        and "run_action(recovery_second_action)" not in GATE06_PROBE
        and '"payload_rebuilt": payload_rebuilt' in GATE06_PROBE
        and '"payload_rebuilt": False' not in GATE06_PROBE,
        "Gate-06 probe does not observe the real queue runner or derives a PASS field as a constant")
require("gate06_lease_trace" in GATE06_LEASE_PROBE
        and "gate06_operator_trace" in GATE06_OPERATOR_PROBE
        and "def wait_due(runtime: ProbeRuntime, row_id: int, timeout: int = 45)" in GATE06_OPERATOR_PROBE
        and 'due_seconds=30' in GATE06_OPERATOR_PROBE,
        "Gate-06 lease or operator executable probe is missing its artifact binding")
require("gate09_compatibility_trace" in GATE09_COMPATIBILITY_PROBE
        and "scheduler-branches.php" in GATE09_COMPATIBILITY_PROBE,
        "Gate-09 compatibility probe omits the isolated scheduler branch check")
require("tests/ui_quality.mjs" in GATE09_PRODUCT_PROBE
        and "plugin-php-tests" in GATE09_PRODUCT_PROBE
        and "pf07_attributable_entries" in GATE09_PRODUCT_PROBE
        and "gate09_product_quality_trace" in GATE09_PRODUCT_PROBE
        and 'require(bool(runtime_root_raw), "PF07_RUNTIME_ROOT is required")' in GATE09_PRODUCT_PROBE
        and 'os.environ.get("PF07_SCRATCH_ROOT", str(Path.home() / "tmp"))' in GATE09_PRODUCT_PROBE,
        "Gate-09 product-quality probe is not bound to real UI, PHP log, machine-check, and artifact observations")
require("gate10_restore_trace" in GATE10_RESTORE_PROBE
        and "REPROVISIONED_RESTORE" in GATE10_RESTORE_PROBE
        and "sha(f\"{shop_instance_id}:{order_id}\") == remote_order_key_sha256" in GATE10_RESTORE_PROBE
        and "len(matching_order_ids) == 1" in GATE10_RESTORE_PROBE
        and "project_resource_count" in GATE10_RESTORE_PROBE
        and "wordpress_quiescence" in GATE10_RESTORE_PROBE
        and "n8n_reprovision_state" in GATE10_RESTORE_PROBE
        and 'environment.update(runtime_env)' in GATE10_RESTORE_PROBE
        and 'os.environ.update(final_env)' in GATE10_RESTORE_PROBE
        and 'b"CREATE DATABASE" not in upper and b"\\nUSE `" not in upper' in GATE10_RESTORE_PROBE
        and 'exec mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"' in GATE10_RESTORE_PROBE
        and "verify_database_credentials" in GATE10_RESTORE_PROBE
        and 'compose(final_root, final_project, "restart", "db", timeout=300)' in GATE10_RESTORE_PROBE
        and "def discard_unprocessed_restore_candidate" in GATE10_RESTORE_PROBE
        and "for _selection_attempt in range(20)" in GATE10_RESTORE_PROBE
        and '"preexisting_remote_collision_count": collision_count' in GATE10_RESTORE_PROBE
        and "hubspot_deals" in GATE10_RESTORE_PROBE
        and "duplicate_replay" in GATE10_RESTORE_PROBE
        and "https_observation" in GATE10_RESTORE_PROBE,
        "Gate-10 probe omits clean-resource, runtime-environment isolation, database-isolation, collision-safe order selection, quiescence, reprovision, remote, duplicate, HTTPS, or artifact evidence")
fixtures = FIXTURE_MANIFEST.get("fixtures")
require(isinstance(fixtures, list) and len(fixtures) == 15,
        "acceptance fixture inventory differs from the 15 canonical records")
require(all(isinstance(item.get("probe_command"), str)
            and item["probe_command"].startswith("scripts/") for item in fixtures),
        "a protected acceptance record is not bound to an exact executable probe")
artifact_aliases = [alias for item in fixtures for alias in item.get("required_artifacts", [])]
shared_aliases = {alias for alias in artifact_aliases if artifact_aliases.count(alias) > 1}
require(shared_aliases == {"exhaustion_attempt_trace", "slack_checkpoint_trace"},
        "independent acceptance runs can overwrite each other's artifact aliases")
require("recorded observation differs from artifact-derived truth" in FIXTURE_RUNNER
        and "derive_fixture_observations" in FIXTURE_RUNNER
        and "protected record is not bound to its exact executable probe" in FIXTURE_RUNNER,
        "protected fixture validation can trust self-declared PASS observations")
require("probe command differs from the exact fixture-bound executable" in EVIDENCE_COLLECTOR
        and "probe observation differs from artifact-derived truth" in EVIDENCE_COLLECTOR
        and 'environment["PF07_FIXTURE_ID"] = fixture["id"]' in EVIDENCE_COLLECTOR
        and "os.replace(stage, destination)" in EVIDENCE_COLLECTOR
        and "fcntl.flock" in EVIDENCE_COLLECTOR,
        "evidence collection is not exact-command-bound, semantic, locked, and atomically promoted")
for fixture_id in (
    "normal-order", "variable-input", "state-non-regression",
    "concurrent-duplicate-suppression", "hmac-rejection",
    "raw-byte-resource-bounds", "stale-lease-recovery",
    "operator-outcome-resolution", "reconciliation-repair",
    "hpos-compatibility", "product-quality", "clean-restore",
):
    require(f'"{fixture_id}"' in ACCEPTANCE_SEMANTICS,
            f"artifact-derived semantic validator is missing: {fixture_id}")

print("PASS: VSL workflow, runtime, credential-reference, and plugin contract checks")
