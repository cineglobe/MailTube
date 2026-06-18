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
    subparsers.add_parser("setup", help="Launch the interactive setup wizard")
    subparsers.add_parser("configure", help="Re-run the interactive setup wizard")
    subparsers.add_parser("doctor", help="Run redacted local diagnostics")
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

        run_setup()
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
