# LumenTP

Version: `v0.1.0`
Protocol version: `LumenTP/1.1`

LumenTP is a small, original, HTTP-like application protocol built from scratch for learning, experimentation, and extension. It keeps the familiar request/response model, but defines its own wire format, methods, framing rules, status codes, and reference behavior.

## What changed in v0.1.0

This version is a deliberate step beyond the barebones prototype:

- the project and protocol are renamed to **LumenTP**
- project metadata was cleaned to stay focused on the protocol itself
- the server now supports **persistent connections** by default
- resources are stored in a **durable file-backed store**
- fetched resources preserve their **Content-Type**
- the server supports simple **Accept** matching for `FETCH`
- error responses can be returned as **structured JSON**
- an optional **token-based authentication** mode is available

## Goals

- Keep the protocol readable on the wire.
- Be explicit about framing, parsing, and limits.
- Stay dependency-light by using only the Python standard library.
- Include real tests, including socket-level integration tests.
- Keep the code easy to evolve into future versions.

## Chosen technologies

- **Language:** Python 3.11+
- **Transport:** TCP sockets
- **Concurrency:** thread-per-connection model using `concurrent.futures`
- **Storage:** file-backed resource store using the local filesystem
- **Serialization:** UTF-8 text for start lines and headers, raw bytes for bodies
- **Testing:** `unittest`
- **Coverage helper:** a small script using the standard-library `trace` module

## Protocol summary

A request looks like this:

```text
FETCH /notes/hello LumenTP/1.1\r\n
Host: localhost\r\n
Accept: text/plain\r\n
\r\n
```

A response looks like this:

```text
LumenTP/1.1 200 OK\r\n
Content-Length: 11\r\n
Content-Type: text/plain\r\n
Connection: keep-alive\r\n
\r\n
hello world
```

### Methods

- `FETCH`: read a resource
- `SUBMIT`: create or store a resource
- `REPLACE`: overwrite or create a resource
- `REMOVE`: delete a resource
- `PING`: lightweight health check

### Status codes

- `200 OK`
- `201 CREATED`
- `204 NO CONTENT`
- `400 BAD REQUEST`
- `401 UNAUTHORIZED`
- `404 NOT FOUND`
- `405 METHOD NOT ALLOWED`
- `406 NOT ACCEPTABLE`
- `411 LENGTH REQUIRED`
- `500 INTERNAL SERVER ERROR`

## Project layout

```text
lumentp/
├── pyproject.toml
├── README.md
├── SPEC.md
├── .gitignore
├── scripts/
│   ├── run_tests.py
│   └── check_coverage.py
├── src/
│   └── lumentp/
│       ├── __init__.py
│       ├── cli.py
│       ├── client.py
│       ├── constants.py
│       ├── errors.py
│       ├── message.py
│       ├── parser.py
│       ├── resource_store.py
│       └── server.py
└── tests/
    ├── test_cli.py
    ├── test_client.py
    ├── test_message.py
    ├── test_parser.py
    ├── test_resource_store.py
    ├── test_server_integration.py
    └── test_server_unit.py
```

## Running the server

```bash
PYTHONPATH=src python -m lumentp.cli server --host 127.0.0.1 --port 8091
```

With durable storage and auth enabled:

```bash
PYTHONPATH=src python -m lumentp.cli server --host 127.0.0.1 --port 8091 --data-dir .runtime/store --token secret-token
```

## Running the client

Fetch:

```bash
PYTHONPATH=src python -m lumentp.cli fetch /hello --host 127.0.0.1 --port 8091 --accept text/plain
```

Submit:

```bash
PYTHONPATH=src python -m lumentp.cli submit /hello --body "hello world" --content-type text/plain --host 127.0.0.1 --port 8091
```

Replace:

```bash
PYTHONPATH=src python -m lumentp.cli replace /hello --body "new value" --content-type text/plain --host 127.0.0.1 --port 8091
```

Remove:

```bash
PYTHONPATH=src python -m lumentp.cli remove /hello --host 127.0.0.1 --port 8091
```

Ping:

```bash
PYTHONPATH=src python -m lumentp.cli ping --host 127.0.0.1 --port 8091
```

## Running tests

```bash
python scripts/run_tests.py
```

## Checking coverage

```bash
python scripts/check_coverage.py
```

## Current test target

- socket-level integration coverage for real request/response flows
- persistence tests for the file-backed store
- unit tests around parser, serialization, CLI dispatch, auth, negotiation, and error handling
- target coverage around `80%+`

## Design choices carried forward and expanded

This version continues the original protocol-design recommendations and applies them more thoroughly:

- **Clear purpose:** lightweight resource exchange over a request/response protocol.
- **Explicit message format:** start line, ordered headers, blank line, optional body.
- **Transport choice:** TCP for ordered and reliable delivery.
- **Framing:** `Content-Length` remains the single body framing rule.
- **Semantics:** methods and status codes are fixed by the spec.
- **Versioning:** every message carries `LumenTP/1.1`.
- **Extensibility:** unknown headers are allowed and preserved.
- **Durability:** resources survive server restarts when using the file-backed store.
- **Negotiation:** `FETCH` can reject a response that does not match `Accept`.
- **Security baseline:** strict parsing, bounded headers, optional token auth, timeouts, and minimal error exposure.
- **Testing:** parser, serializer, store, client, CLI, unit behavior, and end-to-end network behavior are all tested.

## Notes

- This project is intentionally small and educational, but the modifications are chosen to resemble real protocol concerns.
- All code in this repository is original and dependency-light.

## Possible next version ideas

- conditional requests with entity tags
- cache metadata and freshness rules
- bulk operations or batching
- chunked or streaming bodies
- better auth schemes and role-based authorization
- request IDs and structured server logging
