from __future__ import annotations

import argparse
import getpass
import logging
from pathlib import Path

import uvicorn

from mailtube.api.app import create_app
from mailtube.config import Settings
from mailtube.db import Database
from mailtube.security.auth import AuthService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mailtube")
    subparsers = parser.add_subparsers(dest="command")
    serve = subparsers.add_parser("serve", help="Run the MailTube web and worker service")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    setup = subparsers.add_parser("setup", help="Launch the setup wizard")
    setup.add_argument(
        "--non-interactive",
        type=Path,
        metavar="FILE",
        help="Generate configuration from an owner-only JSON setup file",
    )
    configure = subparsers.add_parser("configure", help="Re-run the setup wizard")
    configure.add_argument(
        "--non-interactive",
        type=Path,
        metavar="FILE",
        help="Generate configuration from an owner-only JSON setup file",
    )
    subparsers.add_parser("doctor", help="Run redacted local diagnostics")
    subparsers.add_parser(
        "refresh-compose", help="Refresh generated Compose services while preserving configuration"
    )
    tailscale = subparsers.add_parser(
        "configure-tailscale", help="Apply a detected Tailscale HTTPS origin"
    )
    tailscale.add_argument("dns_name")
    tailscale.add_argument("--https-port", type=int, default=443)
    subparsers.add_parser("hash-password", help="Generate an Argon2id admin password hash")
    backup = subparsers.add_parser("backup", help="Create an online SQLite backup")
    backup.add_argument("destination", type=Path)
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args()
    command = args.command or "serve"
    if command == "hash-password":
        first = getpass.getpass("Admin password: ")
        second = getpass.getpass("Confirm password: ")
        if first != second:
            raise SystemExit("Passwords do not match")
        if len(first) < 12:
            raise SystemExit("Use at least 12 characters")
        print(AuthService.hash_password(first))
        return
    if command in {"setup", "configure"}:
        from mailtube.setup.wizard import run_setup

        run_setup(args.non_interactive)
        return
    if command == "refresh-compose":
        import os

        from mailtube.setup.wizard import refresh_compose

        config_dir = Path(os.getenv("MAILTUBE_CONFIG_DIR", "./mailtube-config")).resolve()
        try:
            path = refresh_compose(config_dir)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"MailTube Compose configuration refreshed at {path}")
        return
    if command == "configure-tailscale":
        import os

        from mailtube.setup.wizard import configure_tailscale

        config_dir = Path(os.getenv("MAILTUBE_CONFIG_DIR", "./mailtube-config")).resolve()
        try:
            url = configure_tailscale(config_dir, args.dns_name, args.https_port)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"MailTube Tailscale URL configured as {url}")
        return
    settings = Settings()
    if command == "doctor":
        from mailtube.setup.doctor import run_doctor

        raise SystemExit(run_doctor(settings))
    if command == "backup":
        Database(settings.db_path).backup(args.destination)
        print(f"Backup written to {args.destination}")
        return
    host = args.host or settings.host
    port = args.port or settings.port
    uvicorn.run(create_app(settings), host=host, port=port, access_log=False)
