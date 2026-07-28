# OFFSET OrderOps · Windows x64

## Download and installation location

Download `pf07-windows-x64-1.0.7.zip` and `SHA256SUMS.txt` from the same
GitHub Release. Before extraction, run the following in PowerShell and compare
the result with the matching line in `SHA256SUMS.txt`:

```powershell
Get-FileHash .\pf07-windows-x64-1.0.7.zip -Algorithm SHA256
```

Do not run a file whose name or SHA-256 differs. Extract the complete verified
ZIP into a new dedicated, non-temporary folder. Paths containing spaces or
Korean characters are supported. After first start, do not move the package
folder or overwrite it with files from another version.

## First run

1. Double-click `PF07-Launcher.exe`.
2. The hub checks prerequisites. If one is missing, follow the numbered
   official installer flow and reopen the same launcher after installation or
   reboot.
3. Select `Start service` and wait until all five services are Ready.
4. Use `Open store` or `Open admin`. Administrator access requires login; use
   `View management account` for the package-local credentials.

The maintained 0-KRW container path for this package is Rancher Desktop with its Moby engine. Docker Desktop is only an optional alternative when the recipient confirms eligibility under its current terms. Python 3.10 or newer is also required. First installation and image acquisition require internet access.

The default `DEMO_MODE` uses synthetic orders and does not contact real
payment, email, HubSpot, or Slack services. `CONNECTED_MODE` can send a real
Slack setup message and create real HubSpot and Slack effects. Read the common
guide first and use it only with protected token files and exact destination
IDs.

## Restart, stop, and update

Command fallbacks are `START-PF07.cmd` and `pf07.cmd`:

```bat
pf07.cmd status
pf07.cmd stop
pf07.cmd start
pf07.cmd restart
pf07.cmd recover
pf07.cmd diagnostics
pf07.cmd evidence-export
```

`stop` stops services while preserving orders, settings, and package-owned
volumes. Reopen the launcher in the same folder later to resume the same state.
To remove data, first create an encrypted backup and use the separately
confirmed removal action.

An update never overwrites the existing folder. Extract the reviewed new
version into a separate folder, then use Controlled update in the new hub to
select the exact supported predecessor extraction. For exact backup, restore,
removal, connected-mode, and optional HTTPS tunnel commands and data effects,
read
[`packaging/common/PACKAGE-README.en.md`](packaging/common/PACKAGE-README.en.md).

## Optional Windows KVM test kit

`pf07-windows-kvm-test-kit-1.0.7.zip` from the same Release is a separate
assistant kit for testing this runnable package in Windows; it is not another
runnable PF07 package. Its quick CMD preflight checks only filename, SHA,
extraction, and launcher version. To test the actual store, administrator,
stop, and recovery paths, follow the full manual workflow in the test kit's
`README.en.md` and `PF07-KVM-TEST.html`.

This Windows artifact is validated on Linux for its PE, scripts, archive, and shared-core contract. It does not claim an owner-KVM full-stack or browser execution result.
