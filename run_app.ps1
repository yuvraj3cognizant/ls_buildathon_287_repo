# Launch the Life Sciences Agentic AI Platform UI using the project venv.
#
#   .\run_app.ps1
#
# Add -Public to bind all interfaces (for demoing from another machine).
param(
    [switch]$Public,
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "venv not found at $python. Create it with: python -m venv venv; .\venv\Scripts\python.exe -m pip install -r requirements.txt"
}

if (-not (Test-Path ".env")) {
    Write-Host "No .env found - creating one from .env.example." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
}

$address = if ($Public) { "0.0.0.0" } else { "localhost" }

& $python -m streamlit run "app/streamlit_app.py" --server.port=$Port --server.address=$address
