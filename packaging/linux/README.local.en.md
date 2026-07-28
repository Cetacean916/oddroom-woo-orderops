# OFFSET OrderOps · Linux local

## Download and installation location

Download `pf07-linux-x86_64-1.0.8.tar.gz` and `SHA256SUMS.txt` from the same
GitHub Release. Before extraction, compare this result with the matching line
in `SHA256SUMS.txt`:

```sh
sha256sum pf07-linux-x86_64-1.0.8.tar.gz
```

Do not run a file whose name or SHA-256 differs. Extract the complete verified
`tar.gz` into a new dedicated, non-temporary folder. Spaces and Korean
characters are supported. After first start, do not move the package folder or
overwrite it with files from another version. Use the package-root
`SHA256SUMS.txt` to check files inside the extraction.

## First run

Run `PF07-Launcher` from the file manager, or trust and open
`PF07-OrderOps.desktop`. The launcher checks Python 3.10 or newer, Docker
Engine, and the Compose plugin. If one is missing, it opens the official
installation guide. Reopen the same launcher after installation or reboot to
continue from the package-local prerequisite state.

Select `Start service` and wait until all five services are Ready before
opening the store or administrator. The default `DEMO_MODE` uses synthetic
orders and does not contact real payment, email, HubSpot, or Slack services.
`CONNECTED_MODE` can send a real Slack setup message and create real HubSpot
and Slack effects. Read the common guide first and use it only with protected
token files and exact destination IDs.

## Restart, stop, and update

Command fallbacks include:

```sh
./pf07 status
./pf07 stop
./pf07 start
./pf07 restart
./pf07 recover
./pf07 diagnostics
./pf07 evidence-export
```

`stop` stops the container services while preserving orders, settings, and
package-owned volumes. Later, reopen the launcher in this folder or run
`./pf07 start` to resume the same state. To remove data, first create an
encrypted backup and use the separately confirmed removal action.

An update never overwrites the existing extraction. Extract the reviewed new
version into a separate folder, then use Controlled update in the new hub to
select the exact supported predecessor extraction. Runtime state exists only
under this extraction's `.pf07/` and its uniquely named Compose project and
volumes.

For exact encrypted backup, restore, removal, connected-mode, and optional
HTTPS tunnel commands and data effects, read
[`packaging/common/PACKAGE-README.en.md`](packaging/common/PACKAGE-README.en.md).
Tunnel failure or shutdown does not stop the local store.
