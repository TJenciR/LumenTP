# LumenTP

Version: `v0.2.0`  
Protocol version: `LumenTP/1.2`

LumenTP is a small, original, HTTP-like application protocol built from scratch for learning, experimentation, and extension. It uses a text-framed request/response model over TCP, while adding practical features such as durable storage, persistent connections, conditional requests, request IDs, and structured logging.

## What changed in v0.2.0

This version adds a more realistic resource lifecycle:

- **ETag-based resource versioning**
- **conditional requests** with `If-None-Match` and `If-Match`
- **cache metadata** on successful `FETCH` responses
- **request IDs** for tracing across client, server, and logs
- **structured JSONL logging**
- improved CLI options for debugging and repeatable workflows
- a stronger README with useful commands for local usage
- a small framing fix so empty `SUBMIT` and `REPLACE` requests still send `Content-Length: 0`

## Goals

- Keep the protocol readable on the wire.
- Be explicit about framing, parsing, and limits.
- Stay dependency-light by using only the Python standard library.
- Include real tests, including socket-level integration tests.
- Keep the code easy to evolve into future versions.

## Chosen technologies

- **Language:** Python 3.11+
- **Transport:** TCP sockets
- **Concurrency:** thread-pool accepted connections, sequential requests per connection
- **Storage:** file-backed resource store using the local filesystem
- **Serialization:** UTF-8 text for start lines and headers, raw bytes for bodies
- **Testing:** `unittest`
- **Coverage helper:** a small script using the standard-library `trace` module
- **Logging:** JSON Lines (`.jsonl`-style plain text)

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
│       ├── logging_utils.py
│       ├── message.py
│       ├── parser.py
│       ├── resource_store.py
│       └── server.py
└── tests/
```

## Useful commands

### 1. Create a local runtime area

```bash
mkdir -p .runtime/store .runtime/logs
```

### 2. Run the server

```bash
PYTHONPATH=src python -m lumentp.cli server \
  --host 127.0.0.1 \
  --port 8091 \
  --data-dir .runtime/store \
  --log-file .runtime/logs/lumentp.log \
  --cache-max-age 120
```

With token authentication enabled:

```bash
PYTHONPATH=src python -m lumentp.cli server \
  --host 127.0.0.1 \
  --port 8091 \
  --data-dir .runtime/store \
  --log-file .runtime/logs/lumentp.log \
  --cache-max-age 120 \
  --token secret-token
```

### 3. Health check

```bash
PYTHONPATH=src python -m lumentp.cli ping --host 127.0.0.1 --port 8091 --show-headers
```

### 4. Create a resource only if it does not already exist

```bash
PYTHONPATH=src python -m lumentp.cli submit /notes/hello \
  --body "hello world" \
  --content-type "text/plain; charset=utf-8" \
  --if-none-match '*' \
  --request-id create-hello-001 \
  --show-headers
```

### 5. Fetch a resource and show response headers

```bash
PYTHONPATH=src python -m lumentp.cli fetch /notes/hello \
  --accept "text/plain" \
  --request-id fetch-hello-001 \
  --show-headers
```

### 6. Re-fetch conditionally using the ETag you got back earlier

Replace `"etag-from-previous-response"` with the actual value.

```bash
PYTHONPATH=src python -m lumentp.cli fetch /notes/hello \
  --accept "text/plain" \
  --if-none-match '"etag-from-previous-response"' \
  --request-id fetch-hello-002 \
  --show-headers
```

### 7. Replace a resource only if the current ETag matches

```bash
PYTHONPATH=src python -m lumentp.cli replace /notes/hello \
  --body "hello again" \
  --content-type "text/plain; charset=utf-8" \
  --if-match '"etag-from-previous-response"' \
  --request-id replace-hello-001 \
  --show-headers
```

### 8. Delete a resource only if the current ETag matches

```bash
PYTHONPATH=src python -m lumentp.cli remove /notes/hello \
  --if-match '"etag-from-previous-response"' \
  --request-id delete-hello-001 \
  --show-headers
```

### 9. Use auth-protected requests

```bash
PYTHONPATH=src python -m lumentp.cli submit /private/doc \
  --body "secret" \
  --content-type text/plain \
  --token secret-token \
  --show-headers
```

### 10. Run the full test suite

```bash
python scripts/run_tests.py
```

### 11. Measure coverage

```bash
python scripts/check_coverage.py
```

### 12. Inspect logs

```bash
tail -f .runtime/logs/lumentp.log
```

## Example raw protocol exchange

Request:

```text
FETCH /notes/hello LumenTP/1.2\r\n
Host: localhost\r\n
Accept: text/plain\r\n
X-Request-Id: demo-fetch-001\r\n
\r\n
```

Response:

```text
LumenTP/1.2 200 OK\r\n
Content-Length: 11\r\n
Content-Type: text/plain; charset=utf-8\r\n
ETag: "a1b2c3d4e5f6a7b8"\r\n
Last-Modified: 2026-04-15T12:00:00Z\r\n
Cache-Control: max-age=120\r\n
X-Request-Id: demo-fetch-001\r\n
Connection: keep-alive\r\n
\r\n
hello world
```

## Supported methods

- `FETCH`: read a resource
- `SUBMIT`: create or store a resource
- `REPLACE`: overwrite or create a resource
- `REMOVE`: delete a resource
- `PING`: lightweight health check

## Current status codes

- `200 OK`
- `201 CREATED`
- `204 NO CONTENT`
- `304 NOT MODIFIED`
- `400 BAD REQUEST`
- `401 UNAUTHORIZED`
- `404 NOT FOUND`
- `405 METHOD NOT ALLOWED`
- `406 NOT ACCEPTABLE`
- `411 LENGTH REQUIRED`
- `412 PRECONDITION FAILED`
- `500 INTERNAL SERVER ERROR`

## Design choices carried forward and expanded

- **Clear purpose:** lightweight resource exchange over a request/response protocol.
- **Explicit message format:** start line, ordered headers, blank line, optional body.
- **Transport choice:** TCP for ordered and reliable delivery.
- **Framing:** `Content-Length` remains the single body framing rule.
- **Semantics:** methods, status codes, and preconditions are fixed by the spec.
- **Versioning:** every message carries `LumenTP/1.2`.
- **Extensibility:** unknown headers are allowed and preserved.
- **Durability:** resources survive server restarts when using the file-backed store.
- **Negotiation:** `FETCH` can reject a response that does not match `Accept`.
- **Caching:** `ETag`, `Last-Modified`, and `Cache-Control` are emitted for stored resources.
- **Traceability:** `X-Request-Id` flows through requests, responses, and logs.
- **Security baseline:** strict parsing, bounded headers, optional token auth, timeouts, and minimal error exposure.
- **Testing:** parser, serializer, store, client, CLI, unit behavior, logging, and end-to-end network behavior are tested.

## Notes

- This project stays intentionally small and educational.
- All code in this repository is original and dependency-light.
- No foreign licensed code or copied implementation references are included.

## Good candidates for the next version

- range or partial responses
- resource listing and query-like filtering
- streaming or chunked transfer support
- stronger auth and roles
- TLS support and secure deployment guidance
- benchmark and load-test scripts
