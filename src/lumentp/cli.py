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
    server_parser.add_argument("--cache-max-age", type=int, default=60)
    server_parser.add_argument("--log-file", default=".runtime/logs/lumentp.log")

    for command in ("fetch", "submit", "replace", "remove"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("target")
        command_parser.add_argument("--host", default="127.0.0.1")
        command_parser.add_argument("--port", type=int, default=8091)
        command_parser.add_argument("--token")
        command_parser.add_argument("--request-id")
        command_parser.add_argument("--show-headers", action="store_true")
        if command == "fetch":
            command_parser.add_argument("--accept")
            command_parser.add_argument("--if-none-match")
        if command in {"submit", "replace"}:
            command_parser.add_argument("--body", default="")
            command_parser.add_argument("--content-type", default="text/plain; charset=utf-8")
            command_parser.add_argument("--if-match")
        if command == "submit":
            command_parser.add_argument("--if-none-match")
        if command == "remove":
            command_parser.add_argument("--if-match")

    ping_parser = subparsers.add_parser("ping")
    ping_parser.add_argument("--host", default="127.0.0.1")
    ping_parser.add_argument("--port", type=int, default=8091)
    ping_parser.add_argument("--request-id")
    ping_parser.add_argument("--show-headers", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "server":
        server = LumenTPServer(
            host=args.host,
            port=args.port,
            data_dir=args.data_dir,
            token=args.token,
            cache_max_age=args.cache_max_age,
            log_file=args.log_file,
        )
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
    if getattr(args, "show_headers", False):
        for name, value in response.headers.items:
            if name.lower() != "content-length":
                print(f"{name}: {value}")
    elif response.headers.get("Content-Type") and response.body:
        print(response.headers.get("Content-Type"))
    if response.body:
        print(response.body.decode("utf-8", errors="replace"))
    return 0


def _run_client_command(client: LumenTPClient, args: argparse.Namespace):
    if args.command == "ping":
        return client.ping(request_id=args.request_id)
    if args.command == "fetch":
        return client.fetch(
            args.target,
            accept=args.accept,
            token=args.token,
            if_none_match=args.if_none_match,
            request_id=args.request_id,
        )
    if args.command == "submit":
        return client.submit(
            args.target,
            args.body.encode("utf-8"),
            content_type=args.content_type,
            token=args.token,
            if_none_match=args.if_none_match,
            if_match=args.if_match,
            request_id=args.request_id,
        )
    if args.command == "replace":
        return client.replace(
            args.target,
            args.body.encode("utf-8"),
            content_type=args.content_type,
            token=args.token,
            if_match=args.if_match,
            request_id=args.request_id,
        )
    if args.command == "remove":
        return client.remove(args.target, token=args.token, if_match=args.if_match, request_id=args.request_id)
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
