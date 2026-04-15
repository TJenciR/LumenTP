# LumenTP Specification

Protocol version: `LumenTP/1.4`

LumenTP is a text-framed request/response protocol over TCP. It is designed as a compact, readable protocol inspired by the basic structure of HTTP, but with its own names and rules.

## 1. Transport

- transport: TCP
- encoding for start lines and headers: UTF-8
- body: raw bytes
- message framing: `Content-Length`
- connections: persistent by default
- close behavior: send `Connection: close` to end after the current exchange

## 2. Message format

### Request

```text
<METHOD> <TARGET> <VERSION>\r\n
Header-Name: value\r\n
Header-Name: value\r\n
\r\n
<optional body bytes>
```

Example:

```text
FETCH /notes/hello LumenTP/1.4
Accept: text/plain
Authorization: Token reader-secret
X-Request-Id: req-001

```

### Response

```text
<VERSION> <STATUS_CODE> <REASON>\r\n
Header-Name: value\r\n
Header-Name: value\r\n
\r\n
<optional body bytes>
```

Example:

```text
LumenTP/1.4 200 OK
Content-Type: text/plain
Content-Length: 5
ETag: "abc123"

hello
```

## 3. Methods

### `PING`
Health check.

### `FETCH`
Retrieve a resource body and headers.

Supports:
- `Accept`
- `If-None-Match`
- `Range`

### `INSPECT`
Retrieve only resource headers and metadata, without the body.

Supports:
- `Accept`
- `If-None-Match`

### `LIST`
List resources under a prefix.

Supports:
- `Accept: application/json`
- `Limit`
- `Offset`
- `Contains`
- `Filter-Content-Type`
- `Sort`
- `Descending`

### `SUBMIT`
Create or update a resource body.

Supports:
- request body
- `Content-Type`
- `Cache-Control`
- `X-Meta-*`
- `If-None-Match`
- `If-Match`

### `REPLACE`
Replace a resource body.

Supports:
- request body
- `Content-Type`
- `Cache-Control`
- `X-Meta-*`
- `If-Match`

### `PATCH`
Update stored metadata without replacing the body.

Request body must be JSON. Supported keys:

```json
{
  "content_type": "text/markdown",
  "cache_control": "no-store",
  "metadata": {
    "stage": "draft",
    "owner": null
  }
}
```

Rules:
- `metadata` values must be strings or `null`
- `null` removes a metadata key
- successful metadata changes update the resource version, last-modified time, and ETag

### `REMOVE`
Delete a resource.

Supports:
- `If-Match`

## 4. Standard headers

### Request headers

- `Host`
- `Authorization: Token <value>`
- `Accept`
- `Content-Type`
- `Content-Length`
- `Connection`
- `If-None-Match`
- `If-Match`
- `Range`
- `Limit`
- `Offset`
- `Contains`
- `Filter-Content-Type`
- `Sort`
- `Descending`
- `Cache-Control`
- `X-Request-Id`
- `X-Meta-*`

### Response headers

- `Content-Type`
- `Content-Length`
- `Connection`
- `ETag`
- `Last-Modified`
- `Cache-Control`
- `Accept-Ranges: bytes`
- `Content-Range`
- `WWW-Authenticate`
- `X-Request-Id`
- `X-Total-Count`
- `X-Meta-*`

## 5. Auth model

LumenTP supports three optional token roles:

- read token: `FETCH`, `INSPECT`, `LIST`
- write token: `SUBMIT`, `REPLACE`, `PATCH`
- admin token: `REMOVE` and everything else

A single shared token mode also exists.

## 6. Resource metadata

Each stored resource includes:

- target
- body
- content type
- ETag
- last-modified timestamp
- version number
- cache-control value
- string metadata map

Metadata is surfaced through `X-Meta-*` headers.

## 7. Status codes

- `200 OK`
- `201 CREATED`
- `204 NO CONTENT`
- `206 PARTIAL CONTENT`
- `304 NOT MODIFIED`
- `400 BAD REQUEST`
- `401 UNAUTHORIZED`
- `404 NOT FOUND`
- `405 METHOD NOT ALLOWED`
- `406 NOT ACCEPTABLE`
- `411 LENGTH REQUIRED`
- `412 PRECONDITION FAILED`
- `416 RANGE NOT SATISFIABLE`
- `500 INTERNAL SERVER ERROR`

## 8. Conditional behavior

### `If-None-Match`
- for `FETCH` and `INSPECT`, matching ETag returns `304 NOT MODIFIED`
- for `SUBMIT`, `If-None-Match: *` blocks creation when the target already exists

### `If-Match`
- for `REPLACE`, `PATCH`, and `REMOVE`, a non-matching ETag returns `412 PRECONDITION FAILED`

## 9. Listing semantics

`LIST` returns JSON like this:

```json
{
  "prefix": "/notes",
  "count": 1,
  "total": 3,
  "limit": 20,
  "offset": 0,
  "contains": "hello",
  "filter_content_type": "text/*",
  "sort": "version",
  "descending": true,
  "items": [
    {
      "target": "/notes/hello",
      "content_type": "text/plain",
      "etag": "\"abc123\"",
      "last_modified": "2026-04-15T20:00:00Z",
      "size": 11,
      "version": 2,
      "cache_control": "max-age=120",
      "metadata": {
        "kind": "note"
      }
    }
  ]
}
```

## 10. Error format

When the client accepts problem JSON, errors use:

```json
{
  "status": 404,
  "reason": "NOT FOUND",
  "detail": "resource /missing was not found"
}
```

Media type:

```text
application/problem+json
```

## 11. Server behavior limits

- maximum header block: 64 KiB
- multiple byte ranges are not supported
- range units other than `bytes` are rejected
- bodies are framed only by `Content-Length`

## 12. Design notes

LumenTP deliberately keeps:

- explicit framing
- simple persistent connections
- strong parser behavior
- small dependency surface
- a reference implementation that is easy to inspect and extend
