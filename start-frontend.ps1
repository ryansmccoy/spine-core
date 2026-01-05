# Market-Spine Trading Desktop Launcher
# Starts the Vite dev server for the trading desktop

$ErrorActionPreference = "Stop"

Write-Host "╔════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   Market-Spine Trading Desktop         ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check if Docker containers are running
Write-Host "Checking backend services..." -ForegroundColor Yellow
$apiContainer = docker ps --filter "name=market-spine-api" --format "{{.Status}}" 2>$null
if (-not $apiContainer) {
    Write-Host "  ⚠ API container not running. Start with:" -ForegroundColor Red
    Write-Host "    cd docker && docker compose up -d" -ForegroundColor Gray
} else {
    Write-Host "  ✓ API: $apiContainer" -ForegroundColor Green
}

$dbContainer = docker ps --filter "name=market-spine-db" --format "{{.Status}}" 2>$null
if ($dbContainer) {
    Write-Host "  ✓ Database: $dbContainer" -ForegroundColor Green
}

Write-Host ""

# Navigate to trading-desktop
$frontendPath = Join-Path $PSScriptRoot "trading-desktop"
if (-not (Test-Path $frontendPath)) {
    Write-Host "Error: trading-desktop folder not found at $frontendPath" -ForegroundColor Red
    exit 1
}

Push-Location $frontendPath

# Check if node_modules exists
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    npm install
}

Write-Host "Starting Vite dev server on port 3000..." -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor Cyan
Write-Host "  API:      http://localhost:8001" -ForegroundColor Cyan
Write-Host ""

# Start the dev server
npm run dev

Pop-Location
