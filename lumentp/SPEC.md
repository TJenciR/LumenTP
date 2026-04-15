# LumenTP/1.1 Specification

## 1. Overview

LumenTP is a text-framed, request/response application protocol that runs over a byte-stream transport, typically TCP.

This document defines version `LumenTP/1.1`.

## 2. Design objectives

1. Be readable on the wire.
2. Be small enough to implement from scratch.
3. Be strict enough to avoid ambiguous parsing.
4. Be extensible through headers and versioning.
5. Be practical enough to test with real network scenarios.
6. Add a few realistic features without losing clarity.

## 3. Connection model

- A client opens a TCP connection to a server.
- A connection may carry **multiple sequential request/response exchanges**.
- Connections are **persistent by default**.
- Either side may request closure with `Connection: close`.
- The reference implementation processes one request at a time per connection.

## 4. Message grammar

### 4.1 Request

```text
METHOD SP TARGET SP VERSION CRLF
*(HEADER CRLF)
CRLF
[BODY]
```

### 4.2 Response

```text
VERSION SP STATUS_CODE SP REASON CRLF
*(HEADER CRLF)
CRLF
[BODY]
```

### 4.3 Header

```text
FIELD_NAME ":" OWS FIELD_VALUE
```

## 5. Encoding rules

- Start lines and headers are encoded as UTF-8 text.
- Bodies are treated as raw bytes.
- Line endings are `\r\n`.
- Message headers end with an empty line: `\r\n\r\n`.
- If a body is present, its size is determined only by `Content-Length`.

## 6. Request fields

### 6.1 METHOD

Valid methods in `LumenTP/1.1`:

- `FETCH`
- `SUBMIT`
- `REPLACE`
- `REMOVE`
- `PING`

### 6.2 TARGET

- Must start with `/`.
- Is case-sensitive.
- Must not contain spaces.
- In this version, the target is treated as an opaque resource key.

### 6.3 VERSION

The only valid version in this specification is `LumenTP/1.1`.

## 7. Response fields

### 7.1 STATUS_CODE

Supported status codes:

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

## 8. Body framing

If a message has a body, it must include `Content-Length` with a non-negative integer value.

If `Content-Length` is present, the parser reads exactly that many bytes after the header block.

For `SUBMIT` and `REPLACE`, the reference implementation requires the request to include `Content-Length`, even when the body is empty. If it is missing, the server returns `411 LENGTH REQUIRED`.

## 9. Header handling

- Header names are case-insensitive for lookup.
- Original insertion order is preserved.
- Unknown headers are allowed.
- If duplicate header names are present, the last one wins for direct lookup in the reference implementation.

## 10. Standard headers in this version

### 10.1 Host

Clients should send `Host`.

### 10.2 Content-Length

Defines body size in bytes.

### 10.3 Content-Type

Represents the media type of the body.

- For `SUBMIT` and `REPLACE`, the server stores this media type with the resource.
- If absent, the reference implementation uses `application/octet-stream`.
- `FETCH` responses include the stored `Content-Type`.

### 10.4 Accept

Used by clients to declare acceptable response media types for `FETCH`.

The reference implementation supports:

- exact matches like `text/plain`
- type wildcards like `text/*`
- full wildcards like `*/*`
- comma-separated lists

Parameters and quality weights are ignored by the reference implementation.

### 10.5 Connection

- `Connection: close` requests that the connection be closed after the current exchange.
- If omitted, the reference implementation keeps the connection open until timeout or peer closure.

### 10.6 Authorization

The reference implementation can be configured to require:

```text
Authorization: Token <token-value>
```

When authentication is enabled:

- `PING` remains public
- all other methods require a matching token
- failures return `401 UNAUTHORIZED`

## 11. Method semantics

### 11.1 FETCH

Returns the bytes stored for the target.

Responses:
- `200 OK` with body when the resource exists and matches `Accept`
- `404 NOT FOUND` when the resource does not exist
- `406 NOT ACCEPTABLE` when the stored representation does not match `Accept`

### 11.2 SUBMIT

Stores the body and its media type at the target.

Responses:
- `201 CREATED` when the target did not exist
- `200 OK` when the target already existed and the representation was replaced

### 11.3 REPLACE

Writes the given body and media type to the target.

Responses:
- `200 OK` when overwriting an existing target
- `201 CREATED` when creating a missing target

### 11.4 REMOVE

Deletes the target.

Responses:
- `204 NO CONTENT` when deletion succeeds
- `404 NOT FOUND` when the target does not exist

### 11.5 PING

A lightweight health check.

Response:
- `200 OK` with body `pong`

## 12. Error handling

Malformed messages produce `400 BAD REQUEST`.

Examples include:

- invalid start line shape
- invalid version
- missing `:` in a header line
- invalid target format
- invalid `Content-Length`
- header block too large
- mismatched body length

Unexpected server failures produce `500 INTERNAL SERVER ERROR`.

The reference implementation can serialize many errors as structured JSON with media type `application/problem+json`.

## 13. Durable storage behavior

The reference implementation stores resources on disk using a local directory.

Each stored resource preserves:

- target
- body bytes
- content type

This makes stored resources survive server restarts.

## 14. Limits in the reference implementation

These are implementation limits, not protocol-law limits:

- maximum header block size: 64 KiB
- socket read timeout: configurable, default 5 seconds
- request handling is sequential within a single connection

## 15. Security notes

This protocol is intentionally simple and still does not define:

- encryption
- authorization scopes or roles
- message signing
- replay protection

The implementation still includes a small hardening baseline:

- strict line parsing
- bounded header size
- target validation
- timeout usage
- optional token authentication
- minimal error exposure

## 16. Versioning strategy

Every request and response carries a protocol version token.

Future versions should:

- keep backward-compatible headers when possible
- introduce new framing rules carefully
- define feature negotiation before making incompatible transport changes
