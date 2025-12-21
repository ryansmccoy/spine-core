# Comprehensive Docker Tier Integration Test
# Runs integration tests against all 3 tiers of spine-core Docker infrastructure

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "spine-core Docker Tier Integration Tests" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$ErrorActionPreference = "Continue"
$resultsFile = "DOCKER_TIER_TEST_RESULTS.md"

# Initialize results file
@"
# spine-core Docker Tier Integration Test Results

> **Test Date:** $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
> **Test Script:** tier_integration_test.ps1
> **Purpose:** Validate all 3 Docker tiers with real API integration tests

---

"@ | Set-Content $resultsFile

function Test-Tier {
    param(
        [string]$TierName,
        [string]$TierLabel,
        [string]$ComposeProfile,
        [int]$WaitSeconds = 15
    )
    
    Write-Host "`n========================================" -ForegroundColor Yellow
    Write-Host "Testing $TierName" -ForegroundColor Yellow
    Write-Host "========================================`n" -ForegroundColor Yellow
    
    # Start tier
    Write-Host "► Starting $TierName containers..." -ForegroundColor Cyan
    
    if ($ComposeProfile -eq "") {
        docker compose -f docker/compose.yml up -d --build 2>&1 | Out-Null
    } else {
        docker compose -f docker/compose.yml --profile $ComposeProfile up -d --build 2>&1 | Out-Null
    }
    
    # Wait for containers to be healthy
    Write-Host "► Waiting $WaitSeconds seconds for containers to become healthy..." -ForegroundColor Cyan
    Start-Sleep -Seconds $WaitSeconds
    
    # Check container status
    Write-Host "► Checking container status..." -ForegroundColor Cyan
    $containers = docker compose -f docker/compose.yml ps --format json 2>&1 | ConvertFrom-Json
    
    # Write container status to results
    @"
## $TierName

### Container Status
``````
"@ | Add-Content $resultsFile
    
    docker compose -f docker/compose.yml ps 2>&1 | Add-Content $resultsFile
    
    @"
``````

"@ | Add-Content $resultsFile
    
    # Run integration tests
    Write-Host "► Running integration tests..." -ForegroundColor Cyan
    
    $testOutput = python integration_test.py "$TierName" 2>&1
    $testExitCode = $LASTEXITCODE
    
    # Display test output
    $testOutput | ForEach-Object { Write-Host $_ }
    
    # Write test results
    @"
### Integration Test Results

``````
$testOutput
``````

**Exit Code:** $testExitCode $(if ($testExitCode -eq 0) { "PASSED" } else { "FAILED" })

---

"@ | Add-Content $resultsFile
    
    # Stop tier
    Write-Host "► Stopping $TierName containers..." -ForegroundColor Cyan
    docker compose -f docker/compose.yml --profile standard --profile full down 2>&1 | Out-Null
    
    Start-Sleep -Seconds 3
    
    return $testExitCode
}

# Navigate to spine-core directory
Set-Location B:\github\py-sec-edgar\spine-core

# Test all tiers
$tier1Result = Test-Tier -TierName "Tier 1: MINIMAL (SQLite)" -TierLabel "minimal" -ComposeProfile "" -WaitSeconds 20
$tier2Result = Test-Tier -TierName "Tier 2: STANDARD (PostgreSQL + Worker)" -TierLabel "standard" -ComposeProfile "standard" -WaitSeconds 30
$tier3Result = Test-Tier -TierName "Tier 3: FULL (TimescaleDB + Redis + Celery + Monitoring)" -TierLabel "full" -ComposeProfile "full" -WaitSeconds 40

# Summary
Write-Host "`n========================================" -ForegroundColor Green
Write-Host "Test Summary" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green

$summaryText = @"

## Test Summary

| Tier | Profile | Status |
|------|---------|--------|
| **Tier 1: Minimal** | (default) | $(if ($tier1Result -eq 0) { "PASSED" } else { "FAILED" }) |
| **Tier 2: Standard** | --profile standard | $(if ($tier2Result -eq 0) { "PASSED" } else { "FAILED" }) |
| **Tier 3: Full** | --profile full | $(if ($tier3Result -eq 0) { "PASSED" } else { "FAILED" }) |

### Overall Result

$( if ($tier1Result -eq 0 -and $tier2Result -eq 0 -and $tier3Result -eq 0) {
    "ALL TIERS PASSED - Docker infrastructure is production-ready"
} else {
    "SOME TIERS FAILED - See details above"
})

---

## Commands to Reproduce

``````bash
# Tier 1 (Minimal)
docker compose -f docker/compose.yml up -d --build
python integration_test.py "Tier 1: MINIMAL"
docker compose -f docker/compose.yml down

# Tier 2 (Standard)
docker compose -f docker/compose.yml --profile standard up -d --build
python integration_test.py "Tier 2: STANDARD"
docker compose -f docker/compose.yml --profile standard down

# Tier 3 (Full)
docker compose -f docker/compose.yml --profile full up -d --build
python integration_test.py "Tier 3: FULL"
docker compose -f docker/compose.yml --profile full down
``````
"@

$summaryText | Add-Content $resultsFile

Write-Host "Tier 1: " -NoNewline
Write-Host $(if ($tier1Result -eq 0) { "PASSED" } else { "FAILED" }) -ForegroundColor $(if ($tier1Result -eq 0) { "Green" } else { "Red" })

Write-Host "Tier 2: " -NoNewline  
Write-Host $(if ($tier2Result -eq 0) { "PASSED" } else { "FAILED" }) -ForegroundColor $(if ($tier2Result -eq 0) { "Green" } else { "Red" })

Write-Host "Tier 3: " -NoNewline
Write-Host $(if ($tier3Result -eq 0) { "PASSED" } else { "FAILED" }) -ForegroundColor $(if ($tier3Result -eq 0) { "Green" } else { "Red" })

Write-Host "`nResults written to: $resultsFile`n" -ForegroundColor Cyan

# Exit with error if any tier failed
if ($tier1Result -ne 0 -or $tier2Result -ne 0 -or $tier3Result -ne 0) {
    exit 1
}
