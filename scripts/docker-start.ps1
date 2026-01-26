# ==============================================================================
# Docker Start Script for spine-core
# ==============================================================================
# Easy way to spin up the market-spine stack
# 
# Usage:
#   .\scripts\docker-start.ps1              # Start basic tier (default)
#   .\scripts\docker-start.ps1 -Tier basic  # Explicit basic tier
#   .\scripts\docker-start.ps1 -Tier intermediate
#   .\scripts\docker-start.ps1 -Tier full
#   .\scripts\docker-start.ps1 -Tier basic -Dev  # With hot-reload
#   .\scripts\docker-start.ps1 -Down        # Stop the stack
# ==============================================================================

param(
    [ValidateSet("basic", "intermediate", "full")]
    [string]$Tier = "basic",
    [switch]$Dev,
    [switch]$Down,
    [switch]$Build
)

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $projectRoot) {
    $projectRoot = "C:\projects\spine-core"
}
Set-Location $projectRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Market Spine - Docker Management" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Project: $projectRoot" -ForegroundColor Gray
Write-Host "Tier: $Tier" -ForegroundColor Gray
Write-Host "Dev Mode: $Dev" -ForegroundColor Gray
Write-Host ""

# Build compose command
$composeFiles = @("-f", "docker-compose.yml", "-f", "docker-compose.$Tier.yml")

if ($Dev) {
    $composeFiles += @("-f", "docker-compose.dev.yml")
}

if ($Down) {
    Write-Host "Stopping Market Spine stack..." -ForegroundColor Yellow
    docker compose @composeFiles down
    Write-Host ""
    Write-Host "Stack stopped!" -ForegroundColor Green
    exit 0
}

# Start the stack
Write-Host "Starting Market Spine ($Tier tier)..." -ForegroundColor Yellow
Write-Host ""

$upArgs = @("up", "-d")
if ($Build) {
    $upArgs = @("up", "-d", "--build")
}

docker compose @composeFiles @upArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host " Stack Started Successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Services:" -ForegroundColor Cyan
    
    switch ($Tier) {
        "basic" {
            Write-Host "  Frontend:  http://localhost:3100" -ForegroundColor White
            Write-Host "  API:       http://localhost:8100" -ForegroundColor White
            Write-Host "  API Docs:  http://localhost:8100/docs" -ForegroundColor White
        }
        "intermediate" {
            Write-Host "  Frontend:  http://localhost:3100" -ForegroundColor White
            Write-Host "  API:       http://localhost:8100" -ForegroundColor White
            Write-Host "  API Docs:  http://localhost:8100/docs" -ForegroundColor White
            Write-Host "  PostgreSQL: localhost:5432" -ForegroundColor Gray
        }
        "full" {
            Write-Host "  Frontend:   http://localhost:3100" -ForegroundColor White
            Write-Host "  API:        http://localhost:8100" -ForegroundColor White
            Write-Host "  API Docs:   http://localhost:8100/docs" -ForegroundColor White
            Write-Host "  TimescaleDB: localhost:5432" -ForegroundColor Gray
            Write-Host "  Redis:      localhost:6379" -ForegroundColor Gray
        }
    }
    
    if ($Dev) {
        Write-Host ""
        Write-Host "Dev Mode:" -ForegroundColor Cyan
        Write-Host "  Frontend Dev: http://localhost:3101 (hot-reload)" -ForegroundColor White
    }
    
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Cyan
    Write-Host "  View logs:   docker compose @composeFiles logs -f" -ForegroundColor Gray
    Write-Host "  Stop stack:  .\scripts\docker-start.ps1 -Tier $Tier -Down" -ForegroundColor Gray
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "Failed to start stack. Check logs above." -ForegroundColor Red
    exit 1
}
