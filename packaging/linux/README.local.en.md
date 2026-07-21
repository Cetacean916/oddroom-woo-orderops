# OFFSET OrderOps · Linux local

Extract the complete `tar.gz` into a new folder; spaces and Korean characters are supported. Run `PF07-Launcher` from the file manager, or trust and open `PF07-OrderOps.desktop`. The launcher checks Python 3.10+, Docker Engine, and the Compose plugin and opens the official installation guide when one is missing. Reopen it after installation to resume the same package-local prerequisite state.

Select `Start runtime` and wait until all five services are Ready before opening the store or admin. Command fallbacks include `./pf07 status`, `./pf07 restart`, `./pf07 diagnostics`, and `./pf07 evidence-export`. Backup, restore, controlled update, and optional HTTPS tunnel actions are available through the same hub and CLI; tunnel failure or shutdown does not stop the local store. Runtime state is created only in this extraction's `.pf07/` and its uniquely named Compose project and volumes.
