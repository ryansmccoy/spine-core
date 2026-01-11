# Prompt B: Add Calculation

**Use this prompt when:** Implementing a new calculation family (rolling averages, aggregations, metrics, ratios, etc.).

---

## Copy-Paste Prompt

```
I need to implement a new calculation for Market Spine.

CONTEXT:
- Read llm-prompts/CONTEXT.md first for repository structure
- Calculations live in: spine-domains/src/spine/domains/{domain}/calculations/{calc_name}.py
- Must inherit from spine.framework.calculations.base.Calculation
- Must register via: from spine.framework.registry import CALCS
- Must be deterministic: same inputs → same outputs
- Must support versioning and capture_id semantics

CALCULATION DETAILS:
- Name: {calc_name}
- Domain: {domain_name}
- Type: {Rolling average / Aggregation / Ratio / Score / Other}
- Inputs: {What tables/data it reads from}
- Output: {What it produces}

---

IMPLEMENTATION CHECKLIST:

### 1. Calculation Class
Location: `spine-domains/src/spine/domains/{domain}/calculations/{calc_name}.py`

Required structure:
```python
from spine.framework.calculations.base import Calculation
from spine.framework.registry import CALCS

@CALCS.register("{calc_name}")
class {CalcName}Calculation(Calculation):
    """
    Computes {description}.
    
    Mathematical Definition:
        {formula or algorithm description}
    
    Inputs:
        - {input_table}: {description}
    
    Output:
        - {output_table}: {description}
    """
    
    # Semantic versioning - increment when logic changes
    version = "1.0.0"
    
    # Fields that define identity (for deduplication)
    invariants = {"source", "calc_type", "period", "window_weeks"}
    
    # Metadata for introspection
    metadata = {
        "description": "{short description}",
        "category": "{rolling|aggregate|ratio|score}",
        "inputs": ["{input_table}"],
        "outputs": ["{output_table}"],
    }
    
    def compute(self, inputs: dict) -> dict:
        """
        Compute the calculation.
        
        Args:
            inputs: Dict containing input data
                - rows: List of input records
                - params: Calculation parameters
        
        Returns:
            Dict with:
                - results: List of output records
                - metadata: Computation metadata
        """
        rows = inputs["rows"]
        params = inputs.get("params", {})
        
        # Your deterministic computation here
        results = self._calculate(rows, params)
        
        return {
            "results": results,
            "metadata": {
                "version": self.version,
                "input_count": len(rows),
                "output_count": len(results),
            }
        }
    
    def compare(self, other: "Calculation", exclude_fields: list = None) -> bool:
        """
        Compare two calculation results for equality.
        
        Excludes audit fields by default.
        """
        exclude = exclude_fields or ["captured_at", "batch_id", "execution_id"]
        
        self_data = {k: v for k, v in self.result.items() if k not in exclude}
        other_data = {k: v for k, v in other.result.items() if k not in exclude}
        
        return self_data == other_data
```

### 2. Pipeline Integration
Location: `spine-domains/src/spine/domains/{domain}/pipelines.py`

Add pipeline class:
```python
from spine.framework.registry import PIPELINES

@PIPELINES.register("compute_{calc_name}")
class Compute{CalcName}Pipeline(Pipeline):
    """
    Pipeline to compute {calc_name} calculation.
    
    Params:
        week_ending: Target week (YYYY-MM-DD)
        tier: Data tier
    """
    
    description = "Compute {calc_name} ({short description})"
    
    spec = {
        "required": ["week_ending", "tier"],
        "optional": {"window_weeks": 6},
        "validators": {
            "week_ending": "valid_week_ending",
            "window_weeks": "positive_int",
        }
    }
    
    def run(self) -> dict:
        week_ending = self.params["week_ending"]
        tier = self.params["tier"]
        window_weeks = self.params.get("window_weeks", 6)
        
        # 1. Quality gate
        ok, missing = require_history_window(
            self.conn, "input_table", week_ending, window_weeks, tier
        )
        if not ok:
            self.record_anomaly("ERROR", "QUALITY_GATE", 
                f"Insufficient history: missing {missing}")
            return {"status": "skipped", "reason": "insufficient_history"}
        
        # 2. Load inputs
        inputs = self._load_inputs(week_ending, tier, window_weeks)
        
        # 3. Compute
        calc = {CalcName}Calculation()
        result = calc.compute({"rows": inputs, "params": self.params})
        
        # 4. Write output with capture_id
        self._write_output(result["results"])
        
        return {
            "status": "complete",
            "rows": len(result["results"]),
            "version": calc.version,
        }
```

### 3. Schema
Location: `spine-domains/src/spine/domains/{domain}/schema/00_tables.sql`

Add output table:
```sql
CREATE TABLE IF NOT EXISTS {domain}_{calc_name} (
    -- Primary key fields
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    
    -- Calculation output fields
    {output_field_1} REAL,
    {output_field_2} REAL,
    
    -- Version tracking
    calc_version TEXT NOT NULL,
    
    -- Capture lineage (REQUIRED)
    capture_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    execution_id TEXT,
    batch_id TEXT,
    
    -- Provenance (for rolled-up data)
    input_min_capture_id TEXT,
    input_max_capture_id TEXT,
    
    -- Quality indicator
    is_complete INTEGER DEFAULT 1,
    weeks_in_window INTEGER,
    
    PRIMARY KEY (week_ending, tier, symbol, capture_id)
);

CREATE INDEX IF NOT EXISTS idx_{calc_name}_lookup 
    ON {domain}_{calc_name}(week_ending, tier, symbol);
```

### 4. Views
Location: `spine-domains/src/spine/domains/{domain}/schema/02_views.sql`

Add latest-per-partition view:
```sql
-- Latest values (one row per week/tier/symbol)
CREATE VIEW IF NOT EXISTS {domain}_{calc_name}_latest AS
SELECT * FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY week_ending, tier, symbol 
               ORDER BY captured_at DESC
           ) as rn
    FROM {domain}_{calc_name}
    WHERE is_complete = 1  -- Quality gate
) WHERE rn = 1;

-- Clean view (excludes partitions with errors)
CREATE VIEW IF NOT EXISTS {domain}_{calc_name}_clean AS
SELECT r.* FROM {domain}_{calc_name}_latest r
WHERE NOT EXISTS (
    SELECT 1 FROM core_anomalies a
    WHERE a.domain = '{domain}'
      AND a.stage = '{CALC_STAGE}'
      AND a.partition_key = r.week_ending || '|' || r.tier
      AND a.severity IN ('ERROR', 'CRITICAL')
      AND a.resolved_at IS NULL
);
```

### 5. Tests
Location: `tests/{domain}/test_{calc_name}.py`

Required tests:
```python
class Test{CalcName}Calculation:
    def test_compute_basic(self, sample_data):
        """Happy path computation."""
        
    def test_compute_empty_input(self):
        """Empty input returns empty result."""
        
    def test_compute_single_row(self, sample_data):
        """Single row computes correctly."""
        
    def test_determinism(self, sample_data):
        """Same inputs produce same outputs."""
        calc = {CalcName}Calculation()
        result1 = calc.compute(sample_data)
        result2 = calc.compute(sample_data)
        assert result1 == result2
        
    def test_version_in_output(self, sample_data):
        """Version is tracked in output."""
        calc = {CalcName}Calculation()
        result = calc.compute(sample_data)
        assert result["metadata"]["version"] == calc.version
        
    def test_compare_excludes_audit_fields(self):
        """compare() ignores audit fields."""


class Test{CalcName}Pipeline:
    def test_full_pipeline(self, db_conn, fixtures):
        """Complete pipeline run."""
        
    def test_idempotency(self, db_conn, fixtures):
        """Same capture_id doesn't duplicate."""
        
    def test_quality_gate_insufficient_history(self, db_conn):
        """Pipeline skips with insufficient history."""
        
    def test_provenance_tracking(self, db_conn, fixtures):
        """Input captures tracked in output."""
```

### 6. Documentation
Location: `docs/calculations/{CALC_NAME}.md`

Required sections:
- Mathematical definition
- Input requirements
- Output schema
- Version history
- Example usage
- Quality gates applied

---

ANTI-PATTERNS TO AVOID:
- ❌ Non-deterministic computation (randomness, timestamps in logic)
- ❌ Missing version field
- ❌ MAX(version) queries (use ROW_NUMBER)
- ❌ Audit fields in determinism checks
- ❌ Missing capture_id in output
- ❌ Missing provenance for rolled-up data
- ❌ Runtime CREATE VIEW
- ❌ Modifying spine-core Calculation base class

---

EXPECTED FILES:
```
spine-domains/src/spine/domains/{domain}/calculations/{calc_name}.py [NEW]
spine-domains/src/spine/domains/{domain}/pipelines.py                [UPDATED]
spine-domains/src/spine/domains/{domain}/schema/00_tables.sql        [UPDATED]
spine-domains/src/spine/domains/{domain}/schema/02_views.sql         [UPDATED]
tests/{domain}/test_{calc_name}.py                                   [NEW]
docs/calculations/{CALC_NAME}.md                                     [NEW]
README.md                                                            [UPDATED]
scripts/build_schema.py                                              [RUN]
```

---

DEFINITION OF DONE:
- [ ] Calculation class with version and invariants
- [ ] compute() is deterministic
- [ ] compare() excludes audit fields
- [ ] Registered in CALCS registry
- [ ] Pipeline class created
- [ ] Quality gate implemented
- [ ] Output table with capture_id and provenance
- [ ] Views for latest and clean
- [ ] build_schema.py run
- [ ] 8+ tests written and passing
- [ ] Documentation created

PROCEED with Change Surface Map, then implementation.
```

---

## Related Documents

- [../CONTEXT.md](../CONTEXT.md) - Repository structure
- [../reference/CAPTURE_SEMANTICS.md](../reference/CAPTURE_SEMANTICS.md) - Capture ID patterns
- [../reference/QUALITY_GATES.md](../reference/QUALITY_GATES.md) - Quality gate patterns
