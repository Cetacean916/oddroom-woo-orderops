# OFFSET OrderOps package

This package starts in credential-free `DEMO_MODE`. It uses synthetic orders and does not contact real payment, email, HubSpot, or Slack services.

## Download verification

Download the platform package and `SHA256SUMS.txt` from the same GitHub
Release. Compare the outer archive SHA-256 before extraction. After extraction,
the package-root `SHA256SUMS.txt` can verify packaged files. Do not run an
archive whose filename or hash differs.

## Prerequisites and first run

- The package-specific supported Docker-compatible runtime with `docker compose`
- Python 3.10 or newer
- Internet access on first install for pinned WordPress dependencies and container images

The graphical launcher checks prerequisites first. If one is missing, it shows an official installer page and a numbered flow, then rechecks on the next launch. Docker Desktop is only an optional alternative when current eligibility is confirmed; the maintained 0-KRW Windows/macOS path is Rancher Desktop with its Moby engine.

## Graphical launch hub

Use the primary OS entrypoint in the package root. On Linux, the direct fallback is:

```sh
./launcher/bin/pf07-hub
```

Select `Start service`, then wait for Ready before opening the store or
administrator. The administrator password is generated on first run and shown
through `View management account` in the package-local hub or the package-local
`credentials` CLI.

## CLI

```sh
./launcher/bin/pf07 --help
./launcher/bin/pf07 preflight
./launcher/bin/pf07 start
./launcher/bin/pf07 status
./launcher/bin/pf07 credentials
./launcher/bin/pf07 open-store
./launcher/bin/pf07 open-admin
./launcher/bin/pf07 stop
./launcher/bin/pf07 restart
./launcher/bin/pf07 recover
./launcher/bin/pf07 diagnostics
./launcher/bin/pf07 evidence-export
./launcher/bin/pf07 backup --passphrase-file /external/path/passphrase.txt
./launcher/bin/pf07 restore /external/path/backup.pf07backup --passphrase-file /external/path/passphrase.txt --confirm 'RESTORE PF07'
./launcher/bin/pf07 update '/previous/PF07 extraction' --confirm 'UPDATE PF07'
./launcher/bin/pf07 tunnel-on --provider cloudflared --executable /external/path/cloudflared --confirm 'ENABLE PF07 TUNNEL'
./launcher/bin/pf07 tunnel-status
./launcher/bin/pf07 tunnel-off --confirm 'DISABLE PF07 TUNNEL'
./launcher/bin/pf07 uninstall --data-choice preserve --confirm 'UNINSTALL PF07'
```

`--help` lists all subcommands, including language, demo scenario, demo-data
reset, and connected setup. Before a command that changes data or can create an
external effect, read that subcommand's `--help` and its confirmation phrase.

`credentials` prints the generated local administrator password. Do not place
its output in chat, logs, screenshots, or Git.

`stop` stops services while preserving package-owned data and volumes. A later
`start` uses the same state. Runtime state and generated material stay under
`.pf07/` plus the package's uniquely named Compose resources.

Korean and English are presentations over one package, one Compose project, one WordPress database, one n8n runtime, and one `SHOP_INSTANCE_ID`. Language switching does not create an order, event, or external effect.

The graphical hub also exposes diagnostics, restart/recovery, evidence ZIP export, authenticated encrypted backup/restore, controlled update, optional HTTPS tunnel, and confirmed package-scoped uninstall. The backup passphrase is never stored in the archive and must be retained separately.

## Demo and connected external effects

`DEMO_MODE` does not contact real HubSpot or Slack services. Before using
`CONNECTED_MODE`, follow `connected-setup --help` and provide protected token
files, HubSpot pipeline/stage IDs, and a Slack channel ID. Keep token files
outside the package and never place token values directly in commands or docs.

With the exact confirmation phrase, `connected-setup` sends one real synthetic
setup message to the selected Slack channel. Later synthetic orders in
`CONNECTED_MODE` can create real effects in the configured HubSpot and Slack
destinations. Real payment and real email delivery remain out of scope.

First start a Ready `DEMO_MODE` runtime, recheck the real destinations, then
connect them with this form:

```sh
./launcher/bin/pf07 connected-setup \
  --hubspot-token-file /protected/path/hubspot-token.txt \
  --hubspot-pipeline-id 'REAL_PIPELINE_ID' \
  --hubspot-initial-stage-id 'REAL_STAGE_ID' \
  --slack-token-file /protected/path/slack-token.txt \
  --slack-channel-id 'REAL_CHANNEL_ID' \
  --confirm-slack-test 'SEND PF07 SLACK TEST'
```

After its connection tests, this command changes the mode to
`CONNECTED_MODE`. To stop synthetic-order delivery to external services and
return to the local demo, run
`./launcher/bin/pf07 mode DEMO_MODE`, then confirm the current mode with
`status`.

## Backup, restore, and removal

- `backup` creates an authenticated encrypted external `.pf07backup` containing
  package state and all three volumes.
- A lost passphrase cannot be recovered. Store it separately from the archive.
- When a current runtime exists, `restore` first creates
  `PF07-Pre-Restore-*.pf07backup` beside the selected archive with the same
  passphrase. It then stops the current writer, replaces the three volumes with
  the selected backup state, and starts the runtime. Retain that automatic
  pre-restore archive with the selected archive.
- `uninstall --data-choice preserve` removes active runtime resources while
  retaining data and package state.
- `uninstall --data-choice remove` removes package-owned volumes and `.pf07`
  state. It is not reversible without an external backup.

The removal command can create its external backup before deleting data:

```sh
./launcher/bin/pf07 uninstall \
  --data-choice remove \
  --backup-output /external/path/PF07-before-uninstall.pf07backup \
  --backup-passphrase-file /protected/path/passphrase.txt \
  --confirm 'UNINSTALL PF07'
```

## Update and tunnel

Never overwrite a running extraction to update it. Extract the reviewed new
archive into a separate folder, then select the exact supported predecessor
from the new hub. The PF07 1.0.8 controlled-update input is an exact reviewed
1.0.7 extraction. Do not select another version or a successor extraction that
already owns runtime state.

Tunnel mode is optional and only attaches to a ready local runtime; local mode
keeps working when the tunnel is off or fails. Keep the `cloudflared` or ngrok
CLI and any ngrok credential configuration outside the package. PF07 exposes
only the storefront and WordPress-authenticated admin routes through its tunnel
policy. After use, require `tunnel-off` and confirm shutdown with
`tunnel-status`.
