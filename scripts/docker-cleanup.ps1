# ==============================================================================
# Docker Cleanup Script for spine-core
# ==============================================================================
# Stops all containers and cleans up Docker resources
# 
# Usage:
#   .\scripts\docker-cleanup.ps1           # Stop all containers
#   .\scripts\docker-cleanup.ps1 -Prune    # Also remove unused resources
#   .\scripts\docker-cleanup.ps1 -All      # Nuclear option - remove everything
# ==============================================================================

param(
    [switch]$Prune,
    [switch]$All
)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Docker Cleanup - spine-core" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Stop all running containers
Write-Host "[1/4] Stopping all running containers..." -ForegroundColor Yellow
$running = docker ps -q
if ($running) {
    docker stop $running 2>$null
    Write-Host "      Stopped $(($running | Measure-Object).Count) container(s)" -ForegroundColor Green
} else {
    Write-Host "      No running containers" -ForegroundColor Gray
}

# Stop docker-compose projects
Write-Host ""
Write-Host "[2/4] Stopping docker-compose projects..." -ForegroundColor Yellow

$composeProjects = @(
    "spine-core",
    "market-spine-basic",
    "market-spine-intermediate", 
    "market-spine-advanced",
    "market-spine-full"
)

foreach ($project in $composeProjects) {
    docker compose -p $project down 2>$null
    Write-Host "      Stopped: $project" -ForegroundColor Gray
}

# Check for Kubernetes (if enabled)
Write-Host ""
Write-Host "[3/4] Checking Kubernetes..." -ForegroundColor Yellow
$kubectx = kubectl config current-context 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "      Kubernetes context: $kubectx" -ForegroundColor Gray
    
    # Try to delete market-spine namespaces
    $namespaces = @("market-spine", "capture-spine-dev")
    foreach ($ns in $namespaces) {
        $exists = kubectl get namespace $ns 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "      Deleting namespace: $ns" -ForegroundColor Yellow
            kubectl delete namespace $ns --ignore-not-found 2>$null
        }
    }
    
    Write-Host ""
    Write-Host "      TIP: To stop Kubernetes pods from auto-restarting:" -ForegroundColor Magenta
    Write-Host "           1. Open Docker Desktop Settings" -ForegroundColor Magenta
    Write-Host "           2. Go to Kubernetes tab" -ForegroundColor Magenta
    Write-Host "           3. Uncheck 'Enable Kubernetes'" -ForegroundColor Magenta
    Write-Host "           4. Click 'Apply & Restart'" -ForegroundColor Magenta
} else {
    Write-Host "      Kubernetes not available (this is fine)" -ForegroundColor Gray
}

# Prune if requested
if ($Prune -or $All) {
    Write-Host ""
    Write-Host "[4/4] Pruning unused Docker resources..." -ForegroundColor Yellow
    
    if ($All) {
        Write-Host "      Removing ALL unused containers, networks, images, and volumes..." -ForegroundColor Red
        docker system prune -a --volumes -f
    } else {
        Write-Host "      Removing unused containers and networks..." -ForegroundColor Yellow
        docker container prune -f
        docker network prune -f
    }
    Write-Host "      Prune complete" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[4/4] Skipping prune (use -Prune flag to clean unused resources)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Cleanup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Show remaining containers
$remaining = docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Select-Object -First 11
Write-Host "Remaining containers:" -ForegroundColor Yellow
Write-Host $remaining
Write-Host ""
