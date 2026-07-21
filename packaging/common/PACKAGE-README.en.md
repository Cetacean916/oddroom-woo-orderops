# OFFSET OrderOps package

This package starts in credential-free `DEMO_MODE`. It uses synthetic orders and does not contact real payment, email, HubSpot, or Slack services.

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

Select `Start runtime`, then wait for Ready before opening the store or admin. The administrator password is generated on first run and shown only through the package-local hub.

## CLI

```sh
./launcher/bin/pf07 preflight
./launcher/bin/pf07 start
./launcher/bin/pf07 status
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

`stop` preserves package-owned data. Runtime state and generated material stay under `.pf07/` plus the package's uniquely named Compose resources.

Korean and English are presentations over one package, one Compose project, one WordPress database, one n8n runtime, and one `SHOP_INSTANCE_ID`. Language switching does not create an order, event, or external effect.

The graphical hub also exposes diagnostics, restart/recovery, evidence ZIP export, authenticated encrypted backup/restore, controlled update, optional HTTPS tunnel, and confirmed package-scoped uninstall. The backup passphrase is never stored in the archive and must be retained separately.

Never overwrite a running extraction to update it. Extract the reviewed new archive into a separate folder, then select the previous extraction from the new hub. Tunnel mode is optional and only attaches to a ready local runtime; local mode keeps working when the tunnel is off or fails. Keep the `cloudflared` or ngrok CLI and any ngrok credential configuration outside the package. PF07 exposes only the storefront and WordPress-authenticated admin routes through its tunnel policy.
