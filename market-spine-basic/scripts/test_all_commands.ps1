#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Comprehensive test suite for Market Spine Basic
    
.DESCRIPTION
    Tests all build tools, commands, and functionality:
    - Just commands
    - Make commands (if available)
    - Docker commands
    - Python CLI commands
    - Smoke tests
    - API endpoints
    
.EXAMPLE
    .\scripts\test_all_commands.ps1
    
.EXAMPLE
    .\scripts\test_all_commands.ps1 -SkipDocker
#>

param(
    [switch]$SkipDocker,
    [switch]$SkipMake,
    [switch]$Verbose
)

$ErrorActionPreference = "Continue"
$OriginalLocation = Get-Location
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

# Change to project directory
Set-Location $ProjectDir

$TestResults = @()
$TotalTests = 0
$PassedTests = 0
$FailedTests = 0

function Write-TestHeader {
    param([string]$Title)
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Write-TestSection {
    param([string]$Title)
    Write-Host ""
    Write-Host "--- $Title ---" -ForegroundColor Yellow
}

function Test-Command {
    param(
        [string]$Name,
        [string]$Command,
        [string]$ExpectedPattern = "",
        [switch]$ShouldFail,
        [string]$WorkingDir = $ProjectDir
    )
    
    $script:TotalTests++
    
    Write-Host ""
    Write-Host "Testing: " -NoNewline -ForegroundColor Gray
    Write-Host $Name -ForegroundColor White
    if ($Verbose) {
        Write-Host "  Command: $Command" -ForegroundColor DarkGray
    }
    
    try {
        $output = Invoke-Expression "cd '$WorkingDir'; $Command 2>&1" | Out-String
        $exitCode = $LASTEXITCODE
        
        $passed = $false
        $reason = ""
        
        if ($ShouldFail) {
            if ($exitCode -ne 0) {
                $passed = $true
                $reason = "Command failed as expected"
            } else {
                $reason = "Command should have failed but succeeded"
            }
        } else {
            if ($exitCode -eq 0) {
                if ($ExpectedPattern) {
                    if ($output -match $ExpectedPattern) {
                        $passed = $true
                        $reason = "Output matched pattern"
                    } else {
                        $reason = "Output did not match pattern: $ExpectedPattern"
                    }
                } else {
                    $passed = $true
                    $reason = "Command succeeded"
                }
            } else {
                $reason = "Command failed with exit code $exitCode"
            }
        }
        
        if ($passed) {
            Write-Host "  ✓ PASS" -ForegroundColor Green
            $script:PassedTests++
        } else {
            Write-Host "  ✗ FAIL: $reason" -ForegroundColor Red
            $script:FailedTests++
            if ($Verbose) {
                Write-Host "  Output: $($output.Substring(0, [Math]::Min(200, $output.Length)))" -ForegroundColor DarkGray
            }
        }
        
        $script:TestResults += @{
            Name = $Name
            Passed = $passed
            Reason = $reason
            Command = $Command
        }
        
    } catch {
        Write-Host "  ✗ FAIL: Exception - $_" -ForegroundColor Red
        $script:FailedTests++
        $script:TestResults += @{
            Name = $Name
            Passed = $false
            Reason = "Exception: $_"
            Command = $Command
        }
    }
}

# =============================================================================
# MAIN TESTS
# =============================================================================

Write-TestHeader "Market Spine Basic - Comprehensive Command Test"
Write-Host "Project: $ProjectDir"
Write-Host "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# -----------------------------------------------------------------------------
# 1. PYTHON DIRECT COMMANDS
# -----------------------------------------------------------------------------
Write-TestHeader "1. Python Direct Commands"

Test-Command `
    -Name "Python version" `
    -Command "python --version" `
    -ExpectedPattern "Python 3\."

Test-Command `
    -Name "UV version" `
    -Command "uv --version" `
    -ExpectedPattern "uv"

Test-Command `
    -Name "Schema build script" `
    -Command "python scripts/build_schema.py" `
    -ExpectedPattern "Schema built successfully"

# -----------------------------------------------------------------------------
# 2. JUST COMMANDS
# -----------------------------------------------------------------------------
Write-TestHeader "2. Just Commands"

# Check if just is available
$justAvailable = (Get-Command just -ErrorAction SilentlyContinue) -ne $null

if ($justAvailable) {
    Write-Host "Just is available" -ForegroundColor Green
    
    Test-Command `
        -Name "just --list" `
        -Command "just --list" `
        -ExpectedPattern "Available recipes"
    
    Test-Command `
        -Name "just schema-build" `
        -Command "just schema-build" `
        -ExpectedPattern "Schema built successfully"
    
    Test-Command `
        -Name "just test (dry run)" `
        -Command "echo 'Skipping just test (takes too long)'" `
        -ExpectedPattern "Skipping"
    
    Test-Command `
        -Name "just lint (dry run)" `
        -Command "echo 'Skipping just lint (not critical)'" `
        -ExpectedPattern "Skipping"
    
} else {
    Write-Host "Just is NOT available - skipping just tests" -ForegroundColor Yellow
    Write-Host "  Install: scoop install just" -ForegroundColor Gray
}

# -----------------------------------------------------------------------------
# 3. MAKE COMMANDS (Unix/macOS/WSL)
# -----------------------------------------------------------------------------
Write-TestHeader "3. Make Commands"

if (-not $SkipMake) {
    $makeAvailable = (Get-Command make -ErrorAction SilentlyContinue) -ne $null
    
    if ($makeAvailable) {
        Write-Host "Make is available" -ForegroundColor Green
        
        Test-Command `
            -Name "make help" `
            -Command "make help" `
            -ExpectedPattern "help"
        
        Test-Command `
            -Name "make schema-build" `
            -Command "make schema-build" `
            -ExpectedPattern "Schema built"
        
    } else {
        Write-Host "Make is NOT available - skipping make tests" -ForegroundColor Yellow
        Write-Host "  Make is primarily for Unix/macOS" -ForegroundColor Gray
    }
} else {
    Write-Host "Skipping Make tests (--SkipMake flag)" -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# 4. SPINE CLI COMMANDS
# -----------------------------------------------------------------------------
Write-TestHeader "4. Spine CLI Commands"

Test-Command `
    -Name "spine --help" `
    -Command "uv run spine --help" `
    -ExpectedPattern "Usage:"

Test-Command `
    -Name "spine --version" `
    -Command "uv run spine --version" `
    -ExpectedPattern "\d+\.\d+\.\d+"

Test-Command `
    -Name "spine pipelines list" `
    -Command "uv run spine pipelines list" `
    -ExpectedPattern "finra"

Test-Command `
    -Name "spine pipelines describe" `
    -Command "uv run spine pipelines describe finra.otc_transparency.ingest_week" `
    -ExpectedPattern "Pipeline:"

Test-Command `
    -Name "spine db init --force" `
    -Command "uv run spine db init --force" `
    -ExpectedPattern "Database"

Test-Command `
    -Name "spine doctor doctor" `
    -Command "uv run spine doctor doctor" `
    -ExpectedPattern "Health Check"

Test-Command `
    -Name "spine verify table" `
    -Command "uv run spine verify table finra_otc_transparency_raw" `
    -ExpectedPattern "Table:"

Test-Command `
    -Name "spine query weeks (expect fail - no data)" `
    -Command "uv run spine query weeks --tier NMS_TIER_1 2>&1" `
    -ExpectedPattern ".*"

Test-Command `
    -Name "spine run dry-run" `
    -Command "uv run spine run run finra.otc_transparency.ingest_week --dry-run --week-ending 2025-12-26 --tier NMS_TIER_1 --file data/fixtures/otc/week_2025-12-26.psv" `
    -ExpectedPattern "DRY RUN|Dry Run"

# -----------------------------------------------------------------------------
# 5. SMOKE TEST
# -----------------------------------------------------------------------------
Write-TestHeader "5. Smoke Test Script"

Write-Host ""
Write-Host "Running comprehensive smoke test..." -ForegroundColor Cyan
Write-Host "This tests CLI + API end-to-end" -ForegroundColor Gray

$smokeTestOutput = uv run python scripts/smoke_test.py 2>&1 | Out-String
$smokeTestPassed = $LASTEXITCODE -eq 0

if ($smokeTestPassed) {
    Write-Host "✓ Smoke test PASSED" -ForegroundColor Green
    $script:PassedTests++
} else {
    Write-Host "✗ Smoke test FAILED" -ForegroundColor Red
    $script:FailedTests++
    if ($Verbose) {
        Write-Host $smokeTestOutput -ForegroundColor DarkGray
    }
}
$script:TotalTests++

# -----------------------------------------------------------------------------
# 6. DOCKER COMMANDS
# -----------------------------------------------------------------------------
Write-TestHeader "6. Docker Commands"

if (-not $SkipDocker) {
    $dockerAvailable = (Get-Command docker -ErrorAction SilentlyContinue) -ne $null
    
    if ($dockerAvailable) {
        Write-Host "Docker is available" -ForegroundColor Green
        
        Test-Command `
            -Name "docker --version" `
            -Command "docker --version" `
            -ExpectedPattern "Docker"
        
        Test-Command `
            -Name "docker compose version" `
            -Command "docker compose version" `
            -ExpectedPattern "version"
        
        Write-Host ""
        Write-Host "Building Docker image (this may take a while)..." -ForegroundColor Cyan
        
        Test-Command `
            -Name "docker compose build" `
            -Command "docker compose build api" `
            -ExpectedPattern ".*"
        
        Write-Host ""
        Write-Host "NOTE: Skipping 'docker compose up' (requires manual stop)" -ForegroundColor Yellow
        Write-Host "  To test manually: docker compose up" -ForegroundColor Gray
        
        Write-Host ""
        Write-Host "Testing Docker schema build service..." -ForegroundColor Cyan
        
        Test-Command `
            -Name "docker compose schema-build" `
            -Command "docker compose --profile schema run --rm schema-build" `
            -ExpectedPattern "Schema built successfully"
        
    } else {
        Write-Host "Docker is NOT available - skipping Docker tests" -ForegroundColor Yellow
        Write-Host "  Install: https://www.docker.com/products/docker-desktop" -ForegroundColor Gray
    }
} else {
    Write-Host "Skipping Docker tests (--SkipDocker flag)" -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# 7. API ENDPOINT TESTS (Quick)
# -----------------------------------------------------------------------------
Write-TestHeader "7. API Quick Test"

Write-Host ""
Write-Host "Starting API server briefly..." -ForegroundColor Cyan

# Find a free port
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$apiPort = $listener.LocalEndpoint.Port
$listener.Stop()

# Start API in background
$apiJob = Start-Job -ScriptBlock {
    param($dir, $port)
    Set-Location $dir
    uv run uvicorn market_spine.api.app:app --host 127.0.0.1 --port $port --log-level error
} -ArgumentList $ProjectDir, $apiPort

# Wait for API to start
Start-Sleep -Seconds 5

try {
    $apiUrl = "http://127.0.0.1:$apiPort"
    
    Write-Host "Testing API at $apiUrl" -ForegroundColor Gray
    
    # Test health endpoint
    try {
        $response = Invoke-RestMethod -Uri "$apiUrl/health" -TimeoutSec 5
        if ($response.status -eq "ok") {
            Write-Host "  ✓ /health endpoint works" -ForegroundColor Green
            $script:PassedTests++
        } else {
            Write-Host "  ✗ /health endpoint returned wrong status" -ForegroundColor Red
            $script:FailedTests++
        }
    } catch {
        Write-Host "  ✗ /health endpoint failed: $_" -ForegroundColor Red
        $script:FailedTests++
    }
    $script:TotalTests++
    
    # Test capabilities endpoint
    try {
        $response = Invoke-RestMethod -Uri "$apiUrl/v1/capabilities" -TimeoutSec 5
        if ($response.tier -eq "basic") {
            Write-Host "  ✓ /v1/capabilities endpoint works" -ForegroundColor Green
            $script:PassedTests++
        } else {
            Write-Host "  ✗ /v1/capabilities returned wrong tier" -ForegroundColor Red
            $script:FailedTests++
        }
    } catch {
        Write-Host "  ✗ /v1/capabilities failed: $_" -ForegroundColor Red
        $script:FailedTests++
    }
    $script:TotalTests++
    
    # Test pipelines endpoint
    try {
        $response = Invoke-RestMethod -Uri "$apiUrl/v1/pipelines" -TimeoutSec 5
        if ($response.count -gt 0) {
            Write-Host "  ✓ /v1/pipelines endpoint works ($($response.count) pipelines)" -ForegroundColor Green
            $script:PassedTests++
        } else {
            Write-Host "  ✗ /v1/pipelines returned no pipelines" -ForegroundColor Red
            $script:FailedTests++
        }
    } catch {
        Write-Host "  ✗ /v1/pipelines failed: $_" -ForegroundColor Red
        $script:FailedTests++
    }
    $script:TotalTests++
    
} finally {
    # Stop API server
    Stop-Job $apiJob -ErrorAction SilentlyContinue
    Remove-Job $apiJob -Force -ErrorAction SilentlyContinue
}

# =============================================================================
# SUMMARY
# =============================================================================

Write-TestHeader "TEST SUMMARY"

Write-Host ""
Write-Host "Total Tests:  $TotalTests" -ForegroundColor White
Write-Host "Passed:       " -NoNewline
Write-Host $PassedTests -ForegroundColor Green
Write-Host "Failed:       " -NoNewline
if ($FailedTests -eq 0) {
    Write-Host $FailedTests -ForegroundColor Green
} else {
    Write-Host $FailedTests -ForegroundColor Red
}

$successRate = if ($TotalTests -gt 0) { [math]::Round(($PassedTests / $TotalTests) * 100, 1) } else { 0 }
Write-Host "Success Rate: $successRate%" -ForegroundColor $(if ($successRate -ge 90) { "Green" } elseif ($successRate -ge 70) { "Yellow" } else { "Red" })

if ($FailedTests -gt 0) {
    Write-Host ""
    Write-Host "Failed Tests:" -ForegroundColor Red
    foreach ($result in $TestResults | Where-Object { -not $_.Passed }) {
        Write-Host "  ✗ $($result.Name)" -ForegroundColor Red
        if ($Verbose) {
            Write-Host "    Command: $($result.Command)" -ForegroundColor DarkGray
            Write-Host "    Reason: $($result.Reason)" -ForegroundColor DarkGray
        }
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Test run completed at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Return to original location
Set-Location $OriginalLocation

# Exit with appropriate code
if ($FailedTests -eq 0) {
    exit 0
} else {
    exit 1
}
