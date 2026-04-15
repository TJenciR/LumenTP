"""Command-line interface for the LumenTP reference project."""

from __future__ import annotations

import argparse
import sys
import time

from .client import LumenTPClient
from .server import LumenTPServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LumenTP reference tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    server_parser = subparsers.add_parser("server", help="run the reference LumenTP server")
    server_parser.add_argument("--host", default="127.0.0.1")
    server_parser.add_argument("--port", type=int, default=8091)
    server_parser.add_argument("--data-dir", default=".runtime/store")
    server_parser.add_argument("--token")

    for command in ("fetch", "submit", "replace", "remove"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("target")
        command_parser.add_argument("--host", default="127.0.0.1")
        command_parser.add_argument("--port", type=int, default=8091)
        command_parser.add_argument("--token")
        if command == "fetch":
            command_parser.add_argument("--accept")
        if command in {"submit", "replace"}:
            command_parser.add_argument("--body", default="")
            command_parser.add_argument("--content-type", default="text/plain; charset=utf-8")

    ping_parser = subparsers.add_parser("ping")
    ping_parser.add_argument("--host", default="127.0.0.1")
    ping_parser.add_argument("--port", type=int, default=8091)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "server":
        server = LumenTPServer(host=args.host, port=args.port, data_dir=args.data_dir, token=args.token)
        print(f"LumenTP server listening on {args.host}:{args.port}")
        server.start()
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nstopping server")
            server.stop()
            return 0

    client = LumenTPClient(host=args.host, port=args.port)
    response = _run_client_command(client, args)
    print(f"{response.status_code} {response.reason}")
    if response.headers.get("Content-Type"):
        print(response.headers.get("Content-Type"))
    if response.body:
        print(response.body.decode("utf-8", errors="replace"))
    return 0


def _run_client_command(client: LumenTPClient, args: argparse.Namespace):
    if args.command == "ping":
        return client.ping()
    if args.command == "fetch":
        return client.fetch(args.target, accept=args.accept, token=args.token)
    if args.command == "submit":
        return client.submit(
            args.target,
            args.body.encode("utf-8"),
            content_type=args.content_type,
            token=args.token,
        )
    if args.command == "replace":
        return client.replace(
            args.target,
            args.body.encode("utf-8"),
            content_type=args.content_type,
            token=args.token,
        )
    if args.command == "remove":
        return client.remove(args.target, token=args.token)
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
