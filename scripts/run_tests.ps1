# PowerShell helper to run tests using .venv_chatterbox
# Usage: ./scripts/run_tests.ps1 -Args "-k test_name"
param(
    [string] $Args = ''
)
$venv = Join-Path -Path $PSScriptRoot -ChildPath "..\.venv_chatterbox\Scripts\python.exe"
if (Test-Path $venv) {
    & $venv -m pytest -- $Args
} else {
    Write-Warning "Could not find .venv_chatterbox at expected location: $venv"
    Write-Host "Falling back to system python"
    python -m pytest -- $Args
}
