/**
 * Orchestrator Lab - Recent Runs Page
 * 
 * Lists recent pipeline executions across all orchestrators.
 * 
 * NOTE: This feature requires Intermediate or Full tier. Basic tier only
 * supports synchronous execution without history tracking.
 */
import { FeatureGate, TierUpgradeMessage } from '../../../api/spineContext';

export default function RecentRunsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-gray-100 mb-4">Orchestrator Lab</h1>
      <FeatureGate
        feature="hasOrchestratorLab"
        fallback={
          <TierUpgradeMessage
            feature="Orchestrator Lab"
            requiredTier="intermediate"
          />
        }
      >
        <p className="text-gray-300">
          Orchestrator Lab content will appear here when connected to an Intermediate or Full tier backend.
        </p>
      </FeatureGate>
    </div>
  );
}
