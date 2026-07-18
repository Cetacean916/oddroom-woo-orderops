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
    "https://api.hubapi.com/crm/objects/2026-03/deals/batch/upsert",
], "HubSpot transport is not the fixed 2026-03 VSL pair")
for node in http_nodes:
    require(node["parameters"].get("authentication") == "genericCredentialType", "HTTP auth is not credential-backed")
    require(node["parameters"].get("genericAuthType") == "httpBearerAuth", "HTTP auth type changed")
    credential = node.get("credentials", {}).get("httpBearerAuth", {})
    require(set(credential) == {"id", "name"}, "workflow contains non-reference credential material")

code = "\n".join(node["parameters"].get("jsCode", "") for node in nodes)
for required in (
    "item.binary?.data?.data",
    "Buffer.from(rawBase64, 'base64')",
    "crypto.timingSafeEqual",
    "$env.ODDROOM_WEBHOOK_HMAC_KEY",
    "created','deal_resolved','deal_upserted','completed",
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
owner_home_paths = set(re.findall("/" + r"home/[^/<\s]+(?:/[^<\s]*)?", COMPOSE))
require(owner_home_paths == {"/" + "home/node/.n8n"}, "compose contains a non-canonical owner-home path")

for column in (
    "event_key", "payload_json", "payload_hash", "attempt_count", "automatic_attempt_count",
    "action_id", "adapter_dispatch_state", "adapter_dispatch_attempt", "lock_token",
    "remote_deal_id", "operator_wait_epoch",
):
    require(column in PLUGIN, f"outbox contract field is absent: {column}")
require("ENGINE=InnoDB" in PLUGIN, "transactional table engine is not explicit")
require("public const GROUP = 'oddroom-orderops'" in PLUGIN, "scheduler group changed")
require("[$rowId]" in PLUGIN, "canonical positional integer argument path is absent")
require("'Error Code','Sanitized Error'" in ADMIN, "admin does not separate stable and sanitized errors")
require("$row->error_code ?? '—', $row->last_error ?? '—'" in ADMIN, "admin omits an error field")
require("echo '<td>' . esc_html((string) $value) . '</td>';" in ADMIN, "admin row values are not escaped")

print("PASS: VSL workflow, runtime, credential-reference, and plugin contract checks")
