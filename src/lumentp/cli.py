"""Command line interface for the LumenTP reference project."""

from __future__ import annotations

import argparse
import sys
import time

from .client import LumenTPClient
from .constants import LIST_SORT_FIELDS
from .server import LumenTPServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lumentp")
    subparsers = parser.add_subparsers(dest="command", required=True)

    server_parser = subparsers.add_parser("server")
    server_parser.add_argument("--host", default="127.0.0.1")
    server_parser.add_argument("--port", type=int, default=8091)
    server_parser.add_argument("--data-dir", default=".runtime/store")
    server_parser.add_argument("--token")
    server_parser.add_argument("--read-token")
    server_parser.add_argument("--write-token")
    server_parser.add_argument("--admin-token")
    server_parser.add_argument("--cache-max-age", type=int, default=60)
    server_parser.add_argument("--log-file", default=".runtime/logs/lumentp.log")

    shared_client_options = {
        "host": {"flags": ["--host"], "kwargs": {"default": "127.0.0.1"}},
        "port": {"flags": ["--port"], "kwargs": {"type": int, "default": 8091}},
        "token": {"flags": ["--token"], "kwargs": {}},
        "request_id": {"flags": ["--request-id"], "kwargs": {}},
        "show_headers": {"flags": ["--show-headers"], "kwargs": {"action": "store_true"}},
    }

    for command in ["fetch", "inspect", "list", "submit", "replace", "patch", "remove"]:
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("target")
        for item in shared_client_options.values():
            command_parser.add_argument(*item["flags"], **item["kwargs"])
        if command in {"fetch", "inspect", "list"}:
            command_parser.add_argument("--accept", default=None if command != "list" else "application/json")
        if command == "fetch":
            command_parser.add_argument("--if-none-match")
            command_parser.add_argument("--range", dest="byte_range")
        if command == "inspect":
            command_parser.add_argument("--if-none-match")
        if command == "list":
            command_parser.add_argument("--limit", type=int)
            command_parser.add_argument("--offset", type=int)
            command_parser.add_argument("--contains")
            command_parser.add_argument("--filter-content-type")
            command_parser.add_argument("--sort", choices=sorted(LIST_SORT_FIELDS))
            command_parser.add_argument("--desc", action="store_true")
        if command in {"submit", "replace"}:
            command_parser.add_argument("--body", default="")
            command_parser.add_argument("--content-type", default="text/plain; charset=utf-8")
            command_parser.add_argument("--cache-control")
            command_parser.add_argument("--meta", action="append", default=[])
            command_parser.add_argument("--if-match")
        if command == "submit":
            command_parser.add_argument("--if-none-match")
        if command == "patch":
            command_parser.add_argument("--content-type-update")
            command_parser.add_argument("--cache-control")
            command_parser.add_argument("--meta", action="append", default=[])
            command_parser.add_argument("--remove-meta", action="append", default=[])
            command_parser.add_argument("--if-match")
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
            read_token=args.read_token,
            write_token=args.write_token,
            admin_token=args.admin_token,
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
            byte_range=args.byte_range,
            request_id=args.request_id,
        )
    if args.command == "inspect":
        return client.inspect(
            args.target,
            accept=args.accept,
            token=args.token,
            if_none_match=args.if_none_match,
            request_id=args.request_id,
        )
    if args.command == "list":
        return client.list(
            args.target,
            token=args.token,
            accept=args.accept,
            limit=args.limit,
            offset=args.offset,
            contains=args.contains,
            filter_content_type=args.filter_content_type,
            sort=args.sort,
            descending=args.desc,
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
            cache_control=args.cache_control,
            metadata=_parse_meta_pairs(args.meta),
            request_id=args.request_id,
        )
    if args.command == "replace":
        return client.replace(
            args.target,
            args.body.encode("utf-8"),
            content_type=args.content_type,
            token=args.token,
            if_match=args.if_match,
            cache_control=args.cache_control,
            metadata=_parse_meta_pairs(args.meta),
            request_id=args.request_id,
        )
    if args.command == "patch":
        return client.patch(
            args.target,
            content_type=args.content_type_update,
            cache_control=args.cache_control,
            metadata=_parse_meta_pairs(args.meta),
            remove_metadata_keys=args.remove_meta,
            token=args.token,
            if_match=args.if_match,
            request_id=args.request_id,
        )
    if args.command == "remove":
        return client.remove(args.target, token=args.token, if_match=args.if_match, request_id=args.request_id)
    raise ValueError(f"unsupported command: {args.command}")


def _parse_meta_pairs(values: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError("metadata items must use key=value")
        key, value = item.split("=", 1)
        metadata[key] = value
    return metadata


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
