import { TierUpgradeMessage, FeatureGate } from '../../api';

export default function JobsPage() {
  return (
    <div className="jobs-page">
      <header className="page-header">
        <h1 className="page-title">Jobs</h1>
      </header>

      <FeatureGate
        feature="hasExecutionHistory"
        fallback={
          <TierUpgradeMessage 
            feature="Job Execution History" 
            requiredTier="intermediate" 
          />
        }
      >
        <p>Job execution history would appear here</p>
      </FeatureGate>
    </div>
  );
}
