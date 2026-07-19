# Environment

## Bootstrap observations

- Docker Engine: `29.6.1`
- Docker Compose: `5.3.1`
- Git: `2.43.0`
- GitHub CLI at bootstrap: system `2.45.0`
- GitHub CLI selected for the final visibility transition: `2.96.0`, installed from the maintained official release in the owner user-global executable path after checksum verification because the bootstrap version did not expose the required visibility-consequence flag; release evidence, not this inventory, establishes whether the transition has occurred
- WordPress CLI container: `2.12.0`
- n8n Community container selected for project creation: `2.25.7`
- n8n task-runner base: `n8nio/runners@sha256:d890fe221de44d75e1900eaf83f4499ad63503bfcc97cb04f0abfe5bc48bc0a6`
- Task-runner dependency builder: `node@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd`
- Custom task-runner image: `oddroom-orderops-task-runners:2.25.7-json-bigint-1.0.0`; active observed image ID `sha256:fee2e9b53d924c5688234f9a85fd5be42999309414f649b45a3748a1556477a1`, user `runner` (`uid=1000`, `gid=1000`)
- Code-node exact-integer parser: project/build-local `json-bigint 1.0.0` with locked `bignumber.js 9.3.1`; external-module allowlist contains exactly those two parser modules, and the builtin allowlist contains only `crypto`
- nginx staging ingress image: `nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10`
- ngrok agent: `3.39.9`, installed in the owner user executable path because host passwordless sudo is unavailable
- Visible execution recorder terminal: `XTerm(390)`, installed from the official Ubuntu `xterm 390-1ubuntu3` package into `$HOME/.local/opt/pf07-xterm` because host passwordless sudo is unavailable; it displays the actual foreground worker and Docker Compose stop/start processes inside the continuous recording
- Toxiproxy: `2.12.0`, official `ghcr.io/shopify/toxiproxy@sha256:9378ed52a28bc50edc1350f936f518f31fa95f0d15917d6eb40b8e376d1a214e`, installed and used as the maintained outage-injection container
- Queue runner mode: `FOREGROUND_WP_CLI`
- Hosting mode: `ON_DEMAND_HTTPS_TUNNEL`
- n8n restore mode: `REPROVISIONED_RESTORE`

The active current version and published version each contain 35 nodes and match the generated source workflow over inherited name, nodes, connections, and settings at semantic SHA-256 `5d787acb6088672809c5fb81d5ac5f3591ba4dcc9adc688bc4e04097dd8aca19`; the active-version pointer equals the current version identity. The active runner preserves signed-64-bit identifiers as exact arbitrary-precision integers through validation and normalizes accepted large identifiers to decimal strings before workflow transport. A signed live request combining the maximum signed-64-bit WooCommerce ID with a 255-code-point astral Unicode field completed; the same maximum in exponent notation reached `duplicate_noop` without another mutation, while signed overflow, negative-ID, 256-code-point, and invalid-UTF-8 requests each returned `400 PAYLOAD_INVALID`. Signed currency-mismatch and decimal-precision-mismatch requests also returned `400 PAYLOAD_INVALID`, and both complete execution traces contained zero HubSpot, association, fault-lookup, or Slack call nodes. After strict-schema activation, seven additional signed requests covering extra top/order/customer/item properties, an invalid calendar date, a non-synthetic email domain, and Unicode overflow each returned `400 PAYLOAD_INVALID`; every complete trace stopped at `Reject Before Side Effects` with zero external-call nodes. After the latest adapter-boundary update, a newly signed negative-ID request again returned `400 PAYLOAD_INVALID`; its four executed nodes ended at `Reject Before Side Effects` and contained no external-call node. A signed lower-rank replay against an authoritative higher-rank Deal returned `200 stale_ignored` from that same active published version immediately after the initial Deal read; its seven executed nodes contained no Contact, Deal-mutation/readback, association, fault-lookup, or Slack node.

The versioned request contract is Draft 2020-12 JSON Schema. An isolated independent validation run used `jsonschema 4.25.1` with `rfc3339-validator 0.1.4`: meta-schema validation passed, the empty-SKU/255-code-point and signed-64 maximum boundaries passed, and ten structural, calendar, Unicode, integer, synthetic-email, rank, and occurrence-source failure fixtures were rejected. This validator install is a test oracle, not a runtime dependency.

The ingress exposes the storefront and the exact production webhook only. It keeps WordPress administration and the n8n editor off the public route, forwards the observed HTTPS scheme, and rejects request bodies above `262144` bytes before n8n executes. Host ports are parameterized so the original, compatibility, and restored Compose projects cannot collide.

Classic and Store API checkout each rejected a non-synthetic identity before order creation. Twelve concurrent otherwise-valid requests sharing one synthetic address-key bucket produced exactly ten admissions and two rate-limit rejections; the single database counter stopped at `10`, and the protected reset command removed that counter and read back zero remaining rate-limit options.

The active PHP 8.3 plugin passed 79 bootstrap assertions. Exact decimal tests preserved `999999999999999999.99` beyond the PHP integer range, found the precise refund that completed that total, kept a total short by `0.01` incomplete, and classified a scientific-notation amount as an invalid fact. The cancellation event path rejected an invalid calendar timestamp instead of accepting PHP date normalization, and the pre-test health option state was restored. Response-disposition assertions also preserve Slack ambiguity for malformed non-429 adapter responses while keeping non-Slack 4xx terminal and 5xx retryable.

## Initialized project runtime

Observed before the first PF07 business action was scheduled:

- WordPress: `7.0.2`
- WooCommerce: `10.9.4`
- Selected WooCommerce currency and decimal precision: `KRW`, exactly `2`
- PHP: `8.3.32`
- Initialized Action Scheduler: `4.0.0`
- Normalized loaded Action Scheduler source: `plugin:action-scheduler/`
- WordPress database schema: `61833`
- Outbox, order-lease, and fault-control engines: `InnoDB`
- Database clock: UTC with microsecond precision

Compatibility is satisfied: WooCommerce 10.9.4 requires WordPress 6.9 or later and PHP 7.4 or later; Action Scheduler 4.0.0 requires WordPress 6.8 or later and PHP 7.2 or later. The selected versions exceed each minimum.

The isolated argument-aware uniqueness preflight passed against this exact initialized version/source identity. Synthetic row IDs `101` and `102` received distinct non-zero action IDs with one exact pending/in-progress candidate each. A duplicate unique schedule for row `101` returned raw ID `0`, the exact resolver reused the original ID, and cancellation left zero candidates. It inserted or changed no business row and consumed no business attempt or lease. Any loaded version/source change invalidates this result and keeps business scheduling disabled until the preflight passes again.

No system-wide package was installed. The exact JSON parser packages were installed project-locally for semantic tests and inside the custom runner image for delivery. The maintained Ubuntu xterm package was extracted into the owner user-local application path for visible runtime recording. Host passwordless sudo is unavailable and was not required because maintained project-local, official user-global, user-local package, and container paths fully supported the selected delivery path.

## Browser and accessibility validation pin

The acceptance storefront runs with WordPress locale `ko_KR`. Bootstrap installs and activates the matching WordPress core language pack after the pinned core update and installs the WooCommerce `ko_KR` language pack after the pinned plugin install. PF07-owned buyer copy, commerce page titles, product copy, the non-monetary payment label, and checkout errors are Korean-first; protected protocol values such as `Synthetic / Buyer`, SKUs, event types, and error codes remain exact where required.

- Browser driver: Playwright `1.61.1`
- Browser executable: host Google Chrome, with its exact observed version recorded in each evidence run
- Accessibility engine and ruleset: axe-core `4.12.1`, default WCAG-impact rules
- Public/storefront mode: `full_document`
- PF07 administrator mode: `scoped`, root selector `.oddroom-orderops`, including every PF07-owned notice, details/action surface, and table inside that root
- Required viewports: `390`, `768`, and `1440` CSS pixels
- Failure threshold: zero `critical` or `serious` violations; no manual PF07-introduced reclassification

The validation also records document `scrollWidth` versus `clientWidth`, broken image responses, clipped primary actions, console errors, and keyboard reachability. The intentionally wide administrator data table must scroll only inside `.oddroom-table-wrap`; page-level horizontal overflow remains a failure.
