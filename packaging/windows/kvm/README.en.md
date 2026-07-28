# PF07 Windows KVM owner test kit

This kit assists testing of `pf07-windows-x64-1.0.7.zip` in Windows. It does
not replace the runnable PF07 package.

## Prerequisites

- `pf07-windows-x64-1.0.7.zip` from the same GitHub Release
- this extracted test-kit folder
- a Windows x64 virtual machine or separate Windows test machine
- for full runtime testing: Rancher Desktop with the Moby engine, Python 3.10
  or newer, and internet access for the first installation

Keep the buyer package as an unmodified ZIP for verification.
`buyer-package-binding.json` defines the expected filename and SHA-256.

## 1. Quick preflight

1. Double-click `RUN-KVM-TEST.cmd`.
2. Select the unmodified `pf07-windows-x64-1.0.7.zip`.
3. Confirm that Archive name, Archive hash, and Launcher found are all `True`.
4. Open `PF07-WINDOWS-KVM-PREFLIGHT.json` on the Windows desktop, confirm all
   preflight PASS conditions below, then retain it.

Preflight PASS conditions:

```json
{
  "archive_name_pass": true,
  "archive_hash_pass": true,
  "unicode_space_extraction_pass": true,
  "launcher_present": true,
  "launcher_version": "1.0.7",
  "actual_full_stack_executed": false
}
```

`actual_full_stack_executed: false` is expected for preflight. The CMD checks
only the filename and SHA-256, extraction into a Korean/space path, launcher
presence, and PE product version. It does not start the PF07 runtime or test the
store, administrator, stop, or recovery paths.

## 2. Full Windows execution test

1. Double-click `PF07-KVM-TEST.html`.
2. Select the same buyer ZIP and require `Result: PASS`.
3. Extract the complete buyer ZIP into a new folder containing Korean
   characters and spaces.
4. Double-click `PF07-Launcher.exe`. Complete graphical prerequisite recovery
   and reopen the launcher after any installation or reboot.
5. Select Start service and wait until all five services are Ready.
6. Open Store and Open Admin from the hub and confirm that administrator access
   requires login. Complete one synthetic order in the store and confirm that
   the same order appears in order management.
7. Use `View detailed status` and record `compose_project`. Switch Korean →
   English → Korean, then reopen detailed status. Confirm the same
   `compose_project`, all five Ready services, and the earlier order.
8. Stop the service in the hub, start it again, and confirm that the same order
   and settings return.
9. In Rancher Desktop's graphical Containers view, stop the `n8n` container
   under the current PF07 Compose project. Use `Restart service` or
   `Recover service` in the hub and confirm all five services return to Ready.
10. Use `View detailed status`, then `Save status record ZIP`. Retain the
    resulting redacted ZIP outside the extracted package.
11. Check only the HTML items that were actually completed, then select
    Download machine-readable result.

## 3. Final confirmation

A full Windows execution claim requires all of the following:

- the preflight PASS fields in `PF07-WINDOWS-KVM-PREFLIGHT.json`;
- `PASS` from the HTML buyer-ZIP verification;
- `archive_binding_pass: true`;
- all ten `steps` values set to `true` in
  `PF07-WINDOWS-KVM-RESULT.json`;
- `all_steps_checked: true`;
- `owner_kvm_execution: true`;
- `completion_state: "OWNER_REPORTED_COMPLETE"`;
- direct observation of a synthetic order, administrator login, language
  switching, stop, restart, and recovery;
- a redacted status-record ZIP retained outside the runnable package.

The checkboxes and `owner_kvm_execution` record owner-performed facts. They are
not automatic execution proof. The HTML marks a result `INCOMPLETE` when the
exact ZIP or all ten checks are missing, but it cannot determine whether a
checked action actually occurred. Do not check a step that was not performed.
