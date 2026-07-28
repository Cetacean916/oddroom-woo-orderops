# OFFSET OrderOps · macOS universal app entry

## Download and installation location

Download `pf07-macos-universal-1.0.8.zip` and `SHA256SUMS.txt` from the same
GitHub Release. Before extraction, compare this result with the matching line:

```sh
shasum -a 256 pf07-macos-universal-1.0.8.zip
```

Do not run a file whose name or SHA-256 differs. Extract the complete verified
ZIP into a new dedicated folder. You may place the complete package folder
under Applications, but do not move `PF07 Launcher.app` alone because it needs
the adjacent shared launcher and payload. After first start, do not move the
package folder or overwrite it with files from another version.

## First run

1. Double-click `PF07 Launcher.app`.
2. If macOS blocks the downloaded app, Control-click it in Finder, choose
   `Open`, then confirm `Open`. This zero-cost portfolio artifact is unsigned
   and not notarized; paid signing is not applied.
3. If the launcher reports a missing Python or container runtime prerequisite,
   use its numbered official link. The maintained 0-KRW path is Rancher
   Desktop with the Moby engine.
4. After installation, logout, or restart, open the same app again. It reads
   package-local progress, rechecks, and resumes.
5. Select `Start service`, wait for Ready, then open the store and
   administrator.

The default `DEMO_MODE` uses synthetic orders and does not contact real
payment, email, HubSpot, or Slack services. `CONNECTED_MODE` can send a real
Slack setup message and create real HubSpot and Slack effects. Read the common
guide first and use it only with protected token files and exact destination
IDs.

## Restart, stop, and update

Use the hub for Korean/English, mode, start, store, administrator, stop,
recovery, backup/restore, controlled update, optional HTTPS tunnel, and
evidence export. Command fallbacks are `pf07.command` for the hub and:

```sh
./pf07 status
./pf07 stop
./pf07 start
./pf07 recover
```

`stop` stops services while preserving orders, settings, and package-owned
volumes. Reopen the app in the same folder later to resume the same state. An
update never overwrites the existing extraction: extract the reviewed new
version into a separate folder, then use the new hub to select the exact
supported predecessor extraction.

For exact backup, restore, removal, connected-mode, and optional HTTPS tunnel
commands and data effects, read
[`packaging/common/PACKAGE-README.en.md`](packaging/common/PACKAGE-README.en.md).

Apple Silicon and Intel use the same portable POSIX app adapter and Python
launcher core. The artifact is validated for app structure, permissions,
architecture declaration, shared core, and archive boundaries; it does not
claim actual Mac container-stack or Safari execution.
