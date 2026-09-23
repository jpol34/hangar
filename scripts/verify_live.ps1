# Sources RUNPOD_API_KEY from Strongbox and runs the live create/resume/stop/delete round-trip
# in verify_live.py. Requires a RUNPOD_API_KEY secret in Strongbox (add one with
# `Set-StrongboxSecret` if it isn't there yet) and `uv sync --extra dev` already run in this repo.

$ErrorActionPreference = "Stop"

$env:RUNPOD_API_KEY = Get-StrongboxSecret -Name "RUNPOD_API_KEY"

try {
    uv run python (Join-Path $PSScriptRoot "verify_live.py")
} finally {
    Remove-Item Env:\RUNPOD_API_KEY -ErrorAction SilentlyContinue
}
