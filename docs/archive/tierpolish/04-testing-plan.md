# Basic Tier Polish - Testing Plan

**Date:** January 3, 2026

## Test Coverage Goals

**Current:** 99 tests passing  
**Target:** 120+ tests passing  
**New tests:** ~25 tests

---

## New Test Files

### 1. test_param_validation.py (~15 tests)

**Purpose:** Test the parameter validation framework

**Test Cases:**

```python
class TestParamDef:
    """Test parameter definition."""
    
    def test_param_def_creation(self):
        """Test creating a parameter definition."""
        
    def test_param_def_with_validator(self):
        """Test parameter with custom validator."""
        
    def test_param_def_with_default(self):
        """Test parameter with default value."""

class TestValidators:
    """Test built-in validators."""
    
    def test_file_exists_validator_valid(self):
        """Test file_exists with existing file."""
        
    def test_file_exists_validator_invalid(self):
        """Test file_exists with missing file."""
        
    def test_enum_value_validator_valid(self):
        """Test enum_value with valid enum."""
        
    def test_enum_value_validator_invalid(self):
        """Test enum_value with invalid value."""
        
    def test_date_format_validator_valid(self):
        """Test date_format with valid date."""
        
    def test_date_format_validator_invalid(self):
        """Test date_format with invalid date."""

class TestPipelineSpec:
    """Test pipeline specification."""
    
    def test_pipeline_spec_creation(self):
        """Test creating a pipeline spec."""
        
    def test_validate_required_params_present(self):
        """Test validation passes with all required params."""
        
    def test_validate_required_params_missing(self):
        """Test validation fails with missing required params."""
        
    def test_validate_optional_params_use_defaults(self):
        """Test optional params use defaults when missing."""
        
    def test_validate_runs_custom_validators(self):
        """Test custom validators are executed."""
        
    def test_validate_returns_validation_result(self):
        """Test validation returns proper result object."""
```

---

### 2. test_error_handling.py (~8 tests)

**Purpose:** Test error handling and classification

**Test Cases:**

```python
class TestBadParamsError:
    """Test BadParamsError exception."""
    
    def test_bad_params_error_creation(self):
        """Test creating BadParamsError with message."""
        
    def test_bad_params_error_with_missing_params(self):
        """Test BadParamsError lists missing params."""

class TestErrorClassification:
    """Test error classification in runner/dispatcher."""
    
    def test_missing_file_path_shows_bad_params(self):
        """Test missing file_path shows BadParamsError, not pipeline not found."""
        # Run: spine run finra.otc_transparency.ingest_week
        # Expected: "Missing required parameter: file_path"
        
    def test_missing_tier_shows_bad_params(self):
        """Test missing tier shows BadParamsError."""
        # Run: spine run finra.otc_transparency.normalize_week -p week_ending=2025-12-05
        # Expected: "Missing required parameter: tier"
        
    def test_unknown_pipeline_shows_not_found(self):
        """Test unknown pipeline shows PipelineNotFoundError."""
        # Run: spine run unknown.pipeline
        # Expected: "Pipeline not found: unknown.pipeline"
        
    def test_error_includes_stack_trace_in_debug(self):
        """Test error includes stack trace when debug enabled."""
        
    def test_error_log_event_names_correct(self):
        """Test log event names match error types."""
        # BadParamsError → execution.params_invalid
        # PipelineNotFoundError → execution.pipeline_not_found
        
    def test_keyerror_inside_pipeline_not_caught_as_not_found(self):
        """Test KeyError from pipeline logic doesn't become 'not found'."""
```

---

### 3. test_verify_commands.py (~6 tests)

**Purpose:** Test verify and query commands

**Test Cases:**

```python
class TestVerifyCommand:
    """Test spine verify command."""
    
    def test_verify_shows_table_counts(self):
        """Test verify displays counts for all tables."""
        # Run after ingesting data
        # Should show: otc_raw, otc_venue_volume, otc_symbol_summary counts
        
    def test_verify_shows_sample_symbols(self):
        """Test verify displays sample top symbols."""
        
    def test_verify_checks_invariants(self):
        """Test verify checks data invariants."""
        # Normalized rows exist for capture_id
        # Aggregates exist for week
        # Rolling metrics computed
        
    def test_verify_with_no_data(self):
        """Test verify handles empty database gracefully."""

class TestQueryCommand:
    """Test spine query command."""
    
    def test_query_table_format(self):
        """Test query with table format output."""
        
    def test_query_json_format(self):
        """Test query with JSON format output."""
        
    def test_query_csv_format(self):
        """Test query with CSV format output."""
        
    def test_query_invalid_sql(self):
        """Test query handles invalid SQL gracefully."""
```

---

### 4. test_backfill_exit_codes.py (~4 tests)

**Purpose:** Test backfill error handling and exit codes

**Test Cases:**

```python
class TestBackfillExitCodes:
    """Test backfill exit codes and error handling."""
    
    def test_backfill_success_returns_zero(self):
        """Test successful backfill returns exit code 0."""
        
    def test_backfill_with_missing_file_returns_nonzero(self):
        """Test backfill with missing file returns exit code 1."""
        
    def test_backfill_error_summary_lists_errors(self):
        """Test backfill error summary includes all errors."""
        # Missing file: week_2026-01-09.psv
        # Should appear in error summary
        
    def test_backfill_partial_success_continues(self):
        """Test backfill continues processing after error."""
        # If week 2 file missing, should still process weeks 1 and 3
```

---

## Modified Test Files

### test_pipelines.py

**Changes:**
- Update tests to expect param validation
- Test that pipelines have `.spec` attribute
- Test spec contains expected params

```python
class TestPipelineSpecs:
    """Test pipeline specifications."""
    
    def test_ingest_pipeline_has_spec(self):
        """Test IngestWeekPipeline has spec defined."""
        
    def test_ingest_spec_requires_file_path(self):
        """Test ingest spec requires file_path param."""
        
    def test_normalize_spec_requires_week_and_tier(self):
        """Test normalize spec requires week_ending and tier."""
```

### test_registry.py

**Changes:**
- Update to test error types
- Verify specs are registered

---

## Integration Tests

### test_end_to_end_workflow.py (new)

**Purpose:** Test complete workflow from ingest to verify

**Test Cases:**

```python
class TestEndToEndWorkflow:
    """Test complete workflow."""
    
    def test_ingest_normalize_aggregate_verify(self):
        """Test full workflow: ingest → normalize → aggregate → verify."""
        # 1. Clean database
        # 2. Run ingest
        # 3. Run normalize
        # 4. Run aggregate
        # 5. Run verify
        # 6. Assert all invariants pass
        
    def test_backfill_then_verify(self):
        """Test backfill followed by verification."""
        
    def test_interactive_mode_simulation(self):
        """Test interactive mode with mocked input."""
```

---

## Performance Tests (Optional)

### test_performance.py (new, optional)

**Purpose:** Ensure new features don't degrade performance

**Test Cases:**

```python
class TestPerformance:
    """Test performance of new features."""
    
    def test_param_validation_overhead_minimal(self):
        """Test param validation adds <5ms overhead."""
        
    def test_progress_tracking_overhead_minimal(self):
        """Test progress tracking adds <10ms overhead."""
```

---

## Test Execution Plan

### Phase 1: Unit Tests
```bash
# Test param validation
uv run pytest tests/test_param_validation.py -v

# Test error handling
uv run pytest tests/test_error_handling.py -v

# Test verify commands
uv run pytest tests/test_verify_commands.py -v

# Test backfill
uv run pytest tests/test_backfill_exit_codes.py -v
```

### Phase 2: Integration Tests
```bash
# Test end-to-end
uv run pytest tests/test_end_to_end_workflow.py -v
```

### Phase 3: Regression Tests
```bash
# Ensure existing tests still pass
uv run pytest tests/ -v
```

### Phase 4: Full Suite
```bash
# Run all tests
uv run pytest tests/ -v --cov=spine --cov-report=term-missing
```

---

## Coverage Goals

**Current Coverage:** Unknown (no coverage tracking yet)  
**Target Coverage:** 85%+

**Focus Areas:**
- Parameter validation: 95%+
- Error handling: 90%+
- CLI commands: 80%+
- Pipeline logic: 85%+ (already high)

---

## Test Data

### Fixtures Needed

1. **Valid parameter sets** for each pipeline
2. **Invalid parameter sets** for testing validation
3. **Sample database** with data for verify tests
4. **Missing files** for backfill error testing

**Location:** `market-spine-basic/tests/fixtures/`

---

## Success Criteria

- [ ] All 120+ tests passing
- [ ] No flaky tests
- [ ] Tests run in <5 seconds
- [ ] Coverage >85%
- [ ] All edge cases covered
- [ ] Windows compatibility verified
