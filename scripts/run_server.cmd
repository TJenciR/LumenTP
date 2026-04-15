@echo off
setlocal

if not exist .runtime\store mkdir .runtime\store
if not exist .runtime\logs mkdir .runtime\logs

lumentp server --host 127.0.0.1 --port 8091 --data-dir .runtime/store --log-file .runtime/logs/lumentp.log --cache-max-age 120 %*
