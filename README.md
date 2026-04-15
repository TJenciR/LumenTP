# LumenTP

Version: `v0.4.0`  
Protocol version: `LumenTP/1.4`

LumenTP is a small, original, HTTP-like application protocol built from scratch for learning, experimentation, and extension. It uses a text-framed request/response model over TCP and includes durable storage, persistent connections, conditional requests, partial responses, resource listing, metadata-only inspection, metadata patching, request tracing, and optional role-based tokens.

## What changed in v0.4.0

This version fixes the Windows command issue from `v0.3.1` and extends the protocol again:

- fixed the packaged Windows helper scripts so they live under `scripts/` correctly
- clarified the **PowerShell** rule that local scripts should be invoked with a relative path like `.\scripts\run_tests.ps1`
- added **`INSPECT`** for metadata-only responses, similar to an HTTP `HEAD`
- added **`PATCH`** for metadata updates without replacing the stored body
- added resource metadata headers with the `X-Meta-*` prefix
- added per-resource `Cache-Control`
- added richer `LIST` filters and sorting
- kept the project dependency-light with standard-library-only tests and coverage tools

## What changed in v0.3.1

This patch focused on **Windows and PyCharm usability**:

- added a proper installed CLI command: `lumentp`
- added Windows helper scripts for setup, server start, tests, and coverage
- expanded the README with **PowerShell**, **Command Prompt**, and **PyCharm** workflows
- kept the protocol and wire behavior at `LumenTP/1.3`

## Project layout

```text
lumentp/
├── pyproject.toml
├── README.md
├── SPEC.md
├── .gitignore
├── scripts/
│   ├── check_coverage.cmd
│   ├── check_coverage.ps1
│   ├── check_coverage.py
│   ├── dev_setup.cmd
│   ├── dev_setup.ps1
│   ├── run_server.cmd
│   ├── run_server.ps1
│   ├── run_tests.cmd
│   ├── run_tests.ps1
│   └── run_tests.py
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

## Recommended setup in PyCharm on Windows

1. Open the `lumentp` folder in PyCharm.
2. Set the project interpreter to **Python 3.11+**.
3. Open the built-in terminal.
4. Run the setup commands below.

## First-time setup

### PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Or:

```powershell
.\scripts\dev_setup.ps1
```

### Command Prompt

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e .
```

Or:

```bat
scripts\dev_setup.cmd
```

## Activate the environment

### PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
```

### Command Prompt

```bat
.venv\Scripts\activate.bat
```

After editable install, the shorter command works:

```powershell
lumentp --help
```

## Why the old Windows command failed

In PowerShell, calling a local script should use a relative path such as:

```powershell
.\scripts\run_tests.ps1
```

or

```powershell
.\scripts\run_tests.cmd
```

Typing only `scripts\run_tests.cmd` can be interpreted incorrectly by PowerShell. Also, the previous zip accidentally flattened several script filenames. This version fixes both issues.

## Useful commands

The commands below are written for **Windows**, especially for the **PyCharm terminal**.

### Start the server

#### PowerShell

```powershell
.\scripts\run_server.ps1
```

#### Command Prompt

```bat
scripts\run_server.cmd
```

### Start the server with role-based tokens

```powershell
lumentp server --host 127.0.0.1 --port 8091 --data-dir .runtime/store --log-file .runtime/logs/lumentp.log --read-token reader-secret --write-token writer-secret --admin-token admin-secret
```

### Health check

```powershell
lumentp ping --host 127.0.0.1 --port 8091 --show-headers
```

### Create a resource only if it does not already exist

```powershell
lumentp submit /notes/hello --body "hello world from LumenTP" --content-type "text/plain; charset=utf-8" --cache-control "max-age=120" --meta kind=note --meta owner=demo --if-none-match '*' --token writer-secret --request-id create-hello-001 --show-headers
```

### Fetch the full resource

```powershell
lumentp fetch /notes/hello --accept "text/plain" --token reader-secret --request-id fetch-hello-001 --show-headers
```

### Inspect only metadata and headers

```powershell
lumentp inspect /notes/hello --accept "text/plain" --token reader-secret --request-id inspect-hello-001 --show-headers
```

### Fetch only a byte range

```powershell
lumentp fetch /notes/hello --accept "text/plain" --range "bytes=0-4" --token reader-secret --request-id fetch-hello-range-001 --show-headers
```

### List resources under a prefix with filters and sorting

```powershell
lumentp list /notes --limit 20 --offset 0 --contains hello --filter-content-type "text/*" --sort version --desc --token reader-secret --request-id list-notes-001 --show-headers
```

### Patch metadata without replacing the body

```powershell
lumentp patch /notes/hello --content-type-update "text/markdown" --cache-control "no-store" --meta stage=draft --remove-meta owner --if-match '"etag-from-previous-response"' --token writer-secret --request-id patch-hello-001 --show-headers
```

### Replace a resource only if the current ETag matches

```powershell
lumentp replace /notes/hello --body "hello again" --content-type "text/plain; charset=utf-8" --if-match '"etag-from-previous-response"' --token writer-secret --request-id replace-hello-001 --show-headers
```

### Delete a resource with the admin token

```powershell
lumentp remove /notes/hello --token admin-secret --request-id delete-hello-001 --show-headers
```

## Run tests

### PowerShell

```powershell
.\scripts\run_tests.ps1
```

You can also run the batch file from PowerShell:

```powershell
.\scripts\run_tests.cmd
```

### Command Prompt

```bat
scripts\run_tests.cmd
```

## Measure coverage

### PowerShell

```powershell
.\scripts\check_coverage.ps1
```

### Command Prompt

```bat
scripts\check_coverage.cmd
```

## Inspect the server log

### PowerShell

```powershell
Get-Content .\runtime\logs\lumentp.log -Tail 20
```

### Command Prompt

```bat
type .runtime\logs\lumentp.log
```

## Current quality snapshot

- tests: **70 passing**
- measured statement coverage for `src/lumentp`: **86.57%**

## Good candidates for the next version

- chunked or streaming bodies
- stronger freshness and cache validation rules
- optional TLS mode for local development
- server-side resource statistics or health endpoints
- richer metadata querying across `LIST`
