$ErrorActionPreference = 'Stop'

New-Item -ItemType Directory -Force -Path '.runtime\store' | Out-Null
New-Item -ItemType Directory -Force -Path '.runtime\logs' | Out-Null

lumentp server --host 127.0.0.1 --port 8091 --data-dir .runtime/store --log-file .runtime/logs/lumentp.log --cache-max-age 120 @args
