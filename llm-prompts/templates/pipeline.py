"""Pipeline template for Market Spine."""
from spine.framework.pipeline import Pipeline
from spine.framework.registry import PIPELINES


@PIPELINES.register("{pipeline_name}")
class {PipelineName}Pipeline(Pipeline):
    """
    {Description of what this pipeline does}.
    
    Params:
        week_ending: Target week (YYYY-MM-DD)
        tier: Data tier
    """
    
    description = "{Short description for logging}"
    
    spec = {
        "required": ["week_ending", "tier"],
        "optional": {},
        "validators": {
            "week_ending": "valid_week_ending",
        }
    }
    
    def run(self) -> dict:
        week_ending = self.params["week_ending"]
        tier = self.params["tier"]
        
        # 1. Quality gate
        # ok, issues = require_precondition(...)
        # if not ok:
        #     self.record_anomaly(...)
        #     return {"status": "skipped"}
        
        # 2. Load inputs
        inputs = self._load_inputs(week_ending, tier)
        
        # 3. Process
        results = self._process(inputs)
        
        # 4. Write output with capture_id
        capture_id = self._generate_capture_id(week_ending, tier)
        self._write_output(results, capture_id)
        
        return {
            "status": "complete",
            "rows": len(results),
            "capture_id": capture_id,
        }
    
    def _generate_capture_id(self, week_ending, tier):
        from datetime import datetime
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        return f"{self.domain}.{self.stage}.{week_ending}|{tier}.{ts}"
