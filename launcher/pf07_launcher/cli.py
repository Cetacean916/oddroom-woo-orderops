from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .core import (
    LauncherError,
    backup,
    configure_connected,
    controlled_update,
    credentials,
    diagnostics,
    export_evidence,
    open_target,
    preflight,
    recover,
    reset_demo,
    restore,
    restart,
    set_demo_scenario,
    set_locale,
    set_mode,
    start,
    status,
    stop,
    tunnel_off,
    tunnel_on,
    tunnel_status,
    open_tunnel_target,
    uninstall,
)


def _emit(value: Any) -> None:
    if isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(prog="pf07", description="OddRoom OrderOps package launcher")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("start", "Start or reconnect the package-owned demo runtime"),
        ("status", "Show local runtime readiness"),
        ("stop", "Stop containers while preserving local demo data"),
        ("restart", "Restart the same package-owned runtime"),
        ("recover", "Recover or reconnect the same package-owned runtime"),
        ("diagnostics", "Show redacted prerequisite, runtime, and integrity diagnostics"),
        ("open-store", "Open the ready storefront"),
        ("open-admin", "Open the ready WordPress admin"),
        ("credentials", "Show the generated package-local admin credential"),
        ("tunnel-status", "Show optional HTTPS tunnel state"),
        ("open-tunnel-store", "Open the allowlisted HTTPS storefront"),
        ("open-tunnel-admin", "Open the protected HTTPS administrator entry"),
    ):
        subparsers.add_parser(command, help=help_text)
    preflight_parser = subparsers.add_parser("preflight", help="Check prerequisites without creating runtime state")
    preflight_parser.add_argument("--open-installer", action="store_true")
    export_parser = subparsers.add_parser("evidence-export", help="Write a redacted machine-readable evidence archive")
    export_parser.add_argument("--output", default=None)
    backup_parser = subparsers.add_parser("backup", help="Create an authenticated encrypted package-local backup")
    backup_parser.add_argument("--output", default=None)
    backup_parser.add_argument("--passphrase-file", required=True)
    restore_parser = subparsers.add_parser("restore", help="Restore one authenticated package-local backup")
    restore_parser.add_argument("archive")
    restore_parser.add_argument("--passphrase-file", required=True)
    restore_parser.add_argument("--confirm", required=True)
    update_parser = subparsers.add_parser("update", help="Move one predecessor state to this reviewed package")
    update_parser.add_argument("predecessor")
    update_parser.add_argument("--confirm", required=True)
    tunnel_on_parser = subparsers.add_parser("tunnel-on", help="Enable the allowlisted optional HTTPS tunnel")
    tunnel_on_parser.add_argument("--confirm", required=True)
    tunnel_on_parser.add_argument("--provider", choices=("cloudflared", "ngrok"), default="cloudflared")
    tunnel_on_parser.add_argument("--executable", default=None)
    tunnel_on_parser.add_argument("--config", default=None)
    tunnel_off_parser = subparsers.add_parser("tunnel-off", help="Disable the package-owned HTTPS tunnel")
    tunnel_off_parser.add_argument("--confirm", required=True)
    uninstall_parser = subparsers.add_parser("uninstall", help="Remove only package-owned runtime resources")
    uninstall_parser.add_argument("--confirm", required=True)
    uninstall_parser.add_argument("--data-choice", choices=("preserve", "remove"), required=True)
    uninstall_parser.add_argument("--backup-output", default=None)
    uninstall_parser.add_argument("--backup-passphrase-file", default=None)
    language_parser = subparsers.add_parser("language", help="Switch presentation language on the same runtime")
    language_parser.add_argument("locale", choices=("ko_KR", "en_US"))
    mode_parser = subparsers.add_parser("mode", help="Switch automation mode on the same business runtime")
    mode_parser.add_argument("mode", choices=("DEMO_MODE", "CONNECTED_MODE"))
    connected_parser = subparsers.add_parser("connected-setup", help="Test and store protected recipient connections")
    connected_parser.add_argument("--hubspot-token-file", required=True)
    connected_parser.add_argument("--hubspot-pipeline-id", required=True)
    connected_parser.add_argument("--hubspot-initial-stage-id", required=True)
    connected_parser.add_argument("--hubspot-alias", default="PF07HubSpotRuntime1")
    connected_parser.add_argument("--slack-token-file", required=True)
    connected_parser.add_argument("--slack-channel-id", required=True)
    connected_parser.add_argument("--slack-alias", default="PF07SlackRuntime1")
    scenario_parser = subparsers.add_parser("scenario", help="Choose the next deterministic demo delivery state")
    scenario_parser.add_argument("scenario", choices=("normal", "fail_once", "terminal", "operator_review"))
    reset_parser = subparsers.add_parser("reset-demo", help="Reset only package-owned demo business data")
    reset_parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    try:
        result: Any
        if args.command == "start":
            result = start()
        elif args.command == "preflight":
            result = preflight(open_installer=args.open_installer)
        elif args.command == "status":
            result = status()
        elif args.command == "stop":
            result = stop()
        elif args.command == "restart":
            result = restart()
        elif args.command == "recover":
            result = recover()
        elif args.command == "diagnostics":
            result = diagnostics()
        elif args.command == "evidence-export":
            result = export_evidence(args.output)
        elif args.command == "backup":
            result = backup(args.output, Path(args.passphrase_file).read_text(encoding="utf-8").rstrip("\r\n"))
        elif args.command == "restore":
            result = restore(
                args.archive,
                Path(args.passphrase_file).read_text(encoding="utf-8").rstrip("\r\n"),
                args.confirm,
            )
        elif args.command == "update":
            result = controlled_update(args.predecessor, args.confirm)
        elif args.command == "tunnel-on":
            result = tunnel_on(args.confirm, args.config, args.provider, args.executable)
        elif args.command == "tunnel-off":
            result = tunnel_off(args.confirm)
        elif args.command == "tunnel-status":
            result = tunnel_status()
        elif args.command == "open-tunnel-store":
            result = {"opened": "tunnel-store", "url": open_tunnel_target("store")}
        elif args.command == "open-tunnel-admin":
            result = {"opened": "tunnel-admin", "url": open_tunnel_target("admin")}
        elif args.command == "uninstall":
            backup_passphrase = None
            if args.backup_passphrase_file:
                backup_passphrase = Path(args.backup_passphrase_file).read_text(encoding="utf-8").rstrip("\r\n")
            result = uninstall(
                args.confirm,
                args.data_choice,
                backup_output=args.backup_output,
                backup_passphrase=backup_passphrase,
            )
        elif args.command == "open-store":
            result = {"opened": "store", "url": open_target("store")}
        elif args.command == "open-admin":
            result = {"opened": "admin", "url": open_target("admin")}
        elif args.command == "language":
            result = set_locale(args.locale)
        elif args.command == "mode":
            result = set_mode(args.mode)
        elif args.command == "connected-setup":
            result = configure_connected({
                "hubspot_token": Path(args.hubspot_token_file).read_text(encoding="utf-8").strip(),
                "hubspot_pipeline_id": args.hubspot_pipeline_id,
                "hubspot_initial_stage_id": args.hubspot_initial_stage_id,
                "hubspot_alias": args.hubspot_alias,
                "slack_token": Path(args.slack_token_file).read_text(encoding="utf-8").strip(),
                "slack_channel_id": args.slack_channel_id,
                "slack_alias": args.slack_alias,
            })
        elif args.command == "scenario":
            result = set_demo_scenario(args.scenario)
        elif args.command == "reset-demo":
            result = reset_demo(args.confirm)
        else:
            result = credentials()
        _emit(result)
        return 0
    except (LauncherError, OSError) as error:
        print(f"PF07 launcher error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
