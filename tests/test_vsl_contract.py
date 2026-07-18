#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = json.loads((ROOT / "workflow/oddroom-orderops-vsl.json").read_text(encoding="utf-8"))
COMPOSE = (ROOT / "infra/compose.yaml").read_text(encoding="utf-8")
PLUGIN = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted((ROOT / "plugin/oddroom-orderops").rglob("*.php"))
)
ADMIN = (ROOT / "plugin/oddroom-orderops/includes/class-oddroom-admin.php").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


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
    "={{ $json.contact_read_url }}",
    "https://api.hubapi.com/crm/objects/2026-03/deals/batch/upsert",
    "https://api.hubapi.com/crm/objects/2026-03/deals/batch/read",
    "={{ $json.association_put_url }}",
    "={{ $json.association_read_url }}",
    "http://wordpress/wp-json/oddroom-orderops/v1/fault-before-slack",
    "https://slack.com/api/chat.postMessage",
], "HubSpot transport is not the fixed 2026-03 complete CRM path")
require([node["parameters"]["method"] for node in http_nodes] == [
    "POST", "POST", "GET", "POST", "POST", "PUT", "GET", "POST", "POST",
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
    "created','deal_resolved','contact_upserted','deal_upserted','associated','completed",
    "idProperty: 'email'",
    "firstname: order.customer.first_name",
    "/associations/default/deal/",
    "$env.SLACK_CHANNEL_ID",
    "SLACK_RETRYABLE_BEFORE_POST",
    "SLACK_OUTCOME_UNKNOWN",
):
    require(required in code, f"workflow invariant missing: {required}")
require("HUBSPOT_RUNTIME_TOKEN" not in code, "runtime token alias entered workflow code")
require(not re.search(r"Bearer\\s+[A-Za-z0-9._-]{12,}", code), "Bearer credential entered workflow")

for digest in (
    "wordpress@sha256:", "mariadb@sha256:", "docker.n8n.io/n8nio/n8n@sha256:",
    "n8nio/runners@sha256:",
):
    require(digest in COMPOSE, f"container digest is not pinned: {digest}")
require('"127.0.0.1:18081:80"' in COMPOSE, "WordPress is not loopback-bound")
require('"127.0.0.1:15678:5678"' in COMPOSE, "n8n editor is not loopback-bound")
require("SLACK_CHANNEL_ID" in COMPOSE, "Slack destination fact is not runtime-bound")
owner_home_paths = set(re.findall("/" + r"home/[^/<\s]+(?:/[^<\s]*)?", COMPOSE))
require(owner_home_paths == {"/" + "home/node/.n8n"}, "compose contains a non-canonical owner-home path")

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

print("PASS: VSL workflow, runtime, credential-reference, and plugin contract checks")
