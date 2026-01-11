# Market Spine Scripts

This directory contains operational scripts and test utilities for Market Spine.

## Production Scripts

### `run_finra_weekly_schedule.py` - **Multi-Week Scheduler** ⭐

**Production-grade scheduler** for FINRA OTC data ingestion with intelligent revision detection.

**Key Features:**
- **Lookback windows** - Process last N weeks (FINRA revises prior weeks)
- **Revision detection** - Skip unchanged weeks using content hash comparison
- **Non-destructive restatements** - capture_id versioning (no deletions)
- **Phased execution** - Ingest → normalize → calcs in correct order
- **Partition isolation** - Failures in one week/tier don't block others
- **Dry-run mode** - Test without database writes

**Quick Start:**
```bash
# Standard weekly run (last 6 weeks)
python scripts/run_finra_weekly_schedule.py --lookback-weeks 6

# Dry-run (no database writes)
python scripts/run_finra_weekly_schedule.py --mode dry-run

# Backfill specific weeks
python scripts/run_finra_weekly_schedule.py --weeks 2025-12-15,2025-12-22

# Force restatement (ignore revision detection)
python scripts/run_finra_weekly_schedule.py --force --lookback-weeks 4

# Verbose output
python scripts/run_finra_weekly_schedule.py --verbose
```

**Exit Codes:**
- `0` - Success (all weeks processed)
- `1` - Partial failure (some partitions failed)
- `2` - Critical failure (DB down, invalid config)

**Deployment:**
- cron: See [docs/ops/scheduling.md](../docs/ops/scheduling.md)
- Kubernetes: See K8s CronJob examples in scheduling.md
- OpenShift: See OpenShift-specific configuration in scheduling.md

**Documentation:**
- [Multi-Week Scheduler Design](../docs/ops/multi-week-scheduler.md) - Architecture details
- [Scheduling Guide](../docs/ops/scheduling.md) - Deployment examples

---

## Test Scripts

### 1. `test_all_commands.ps1` - **Comprehensive Command Test Suite**

Tests all build tools, commands, and functionality in one go.

**What it tests:**
- ✅ Python direct commands
- ✅ Just commands (if installed)
- ✅ Make commands (if installed)
- ✅ Spine CLI commands
- ✅ Smoke test script
- ✅ Docker build and commands
- ✅ API endpoints (quick validation)

**Usage:**
```powershell
# Run all tests
.\scripts\test_all_commands.ps1

# Skip Docker tests (faster)
.\scripts\test_all_commands.ps1 -SkipDocker

# Skip Make tests
.\scripts\test_all_commands.ps1 -SkipMake

# Verbose output
.\scripts\test_all_commands.ps1 -Verbose

# Combine flags
.\scripts\test_all_commands.ps1 -SkipDocker -Verbose
```

**Expected output:**
- Green ✓ for passing tests
- Red ✗ for failing tests
- Summary with pass/fail counts and success rate

---

### 2. `smoke_test.py` - **End-to-End CLI + API Test**

Comprehensive smoke test that validates core functionality using fixture data.

**What it tests:**
- Database initialization
- Pipeline listing and description
- Pipeline execution (ingest + normalize)
- Query commands
- Verify commands
- API health check
- API capabilities
- API pipelines endpoint
- API query endpoints
- API pipeline execution (dry-run)

**Usage:**
```bash
# Run smoke test
uv run python scripts/smoke_test.py

# From project root
cd market-spine-basic
uv run python scripts/smoke_test.py
```

**Features:**
- Uses temporary database (no cleanup needed)
- Uses fixture data (no downloads required)
- Tests both CLI and API
- Graceful handling of Windows encoding issues
- Colored output with clear pass/fail indicators

**Exit codes:**
- `0` - All tests passed
- `1` - One or more tests failed

---

### 3. `test_cli_comprehensive.ps1` - **CLI-Focused Test Suite**

PowerShell script for testing CLI commands, parameter passing, and error handling.

**What it tests:**
- Help commands
- Pipeline discovery
- Database commands
- Verify commands
- Query commands
- Three-way parameter passing (--options, key=value, -p flags)
- Tier normalization
- Special flags (--explain-source, --dry-run, --help-params)
- Error handling

**Usage:**
```powershell
.\market-spine-basic\test_cli_comprehensive.ps1

# Or from scripts directory
cd market-spine-basic
.\test_cli_comprehensive.ps1
```

---

### 4. `build_schema.py` - **Schema Build Script**

Builds the combined schema.sql from modular schema files.

**Usage:**
```bash
# Build schema
python scripts/build_schema.py

# Or via build tools
just schema-build
make schema-build
docker compose --profile schema run --rm schema-build
```

**Output:**
- `market-spine-basic/migrations/schema.sql` (37KB+)
- Validates all module files exist
- Shows size and module count

---

## Recommended Testing Workflow

### Quick Validation (1-2 minutes)
```powershell
# Test core commands only
.\scripts\test_all_commands.ps1 -SkipDocker
```

### Full Validation (5-10 minutes)
```powershell
# Test everything including Docker
.\scripts\test_all_commands.ps1
```

### Deep Validation (15+ minutes)
```bash
# Run all test scripts
.\scripts\test_all_commands.ps1
uv run python scripts/smoke_test.py
.\test_cli_comprehensive.ps1
pytest tests/ -v
```

---

## CI/CD Integration

### GitHub Actions Example
```yaml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      
      - name: Run smoke test
        run: uv run python scripts/smoke_test.py
        working-directory: market-spine-basic
      
      - name: Run pytest
        run: uv run pytest tests/ -v
        working-directory: market-spine-basic
```

---

## Troubleshooting

### Common Issues

**1. "Just not found"**
- Install: `scoop install just` (Windows)
- Or skip: `.\scripts\test_all_commands.ps1 -SkipMake`

**2. "Docker not available"**
- Install Docker Desktop
- Or skip: `.\scripts\test_all_commands.ps1 -SkipDocker`

**3. "UnicodeEncodeError on Windows"**
- Smoke test handles this automatically
- Uses UTF-8 reconfiguration for console
- Looks for success markers in stderr

**4. "API tests fail"**
- Check port 8000 isn't already in use
- Smoke test uses random free ports
- Kill any running uvicorn processes

**5. "Smoke test timeout"**
- Increase timeout in smoke_test.py
- Check system resources
- Try running components individually

---

## Test Coverage

| Component | smoke_test.py | test_cli_comprehensive.ps1 | test_all_commands.ps1 |
|-----------|---------------|----------------------------|------------------------|
| CLI Commands | ✅ | ✅ | ✅ |
| API Endpoints | ✅ | ❌ | ✅ |
| Pipeline Execution | ✅ | ❌ | ❌ |
| Database Init | ✅ | ✅ | ✅ |
| Query Commands | ✅ | ✅ | ✅ |
| Parameter Passing | ❌ | ✅ | ✅ |
| Build Tools (Just/Make) | ❌ | ❌ | ✅ |
| Docker | ❌ | ❌ | ✅ |
| Error Handling | ⚠️  | ✅ | ⚠️  |

**Legend:** ✅ Full coverage | ⚠️  Partial coverage | ❌ No coverage

---

## Adding New Tests

### To smoke_test.py
```python
def test_my_feature(base_url: str) -> bool:
    """Test my new feature."""
    print_step("Testing my feature")
    
    try:
        # Test code here
        print_ok("Feature works!")
        return True
    except Exception as e:
        print_fail(f"Feature failed: {e}")
        return False

# Add to main():
results.append(("My Feature", test_my_feature(base_url)))
```

### To test_all_commands.ps1
```powershell
Test-Command `
    -Name "My new command" `
    -Command "uv run spine my-command --arg value" `
    -ExpectedPattern "expected output"
```

### To test_cli_comprehensive.ps1
```powershell
Write-TestHeader "My New Feature"
$output = uv run spine my-command 2>&1
$passed = ($output -join " ") -match "expected"
Write-TestResult "My command test" $passed
```

---

## Maintenance

- **Update tests when adding commands** - Add to appropriate test script
- **Update expected patterns** - If output format changes
- **Add new test categories** - For major new features
- **Keep fixture data current** - Update week_2025-12-26.psv if schema changes
- **Document test skips** - Explain why certain tests are skipped

---

## Future Enhancements

- [ ] Add pytest integration tests
- [ ] Add performance benchmarks
- [ ] Add coverage reporting
- [ ] Add mutation testing
- [ ] Add contract tests for API
- [ ] Add load tests for API
- [ ] Add Docker health checks validation
- [ ] Add multi-platform testing (Linux, macOS, Windows)
