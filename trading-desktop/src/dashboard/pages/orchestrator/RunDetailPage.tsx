/**
 * Orchestrator Lab - Run Detail Page
 * 
 * Shows detailed view of a single execution including tasks, events, and artifacts.
 * 
 * NOTE: This feature requires Intermediate or Full tier. Basic tier only
 * supports synchronous execution without history tracking.
 */
import { useParams, Link } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import { FeatureGate, TierUpgradeMessage } from '../../../api/spineContext';

export default function RunDetailPage() {
  const { executionId } = useParams<{ executionId: string }>();

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <Link
          to="/dashboard/orchestrator"
          className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition"
        >
          <ArrowLeftIcon className="w-5 h-5" />
        </Link>
        <div>
          <h1 className="text-2xl font-semibold text-gray-100">
            Run Detail
          </h1>
          {executionId && (
            <p className="text-sm text-gray-400 font-mono mt-1">
              {executionId}
            </p>
          )}
        </div>
      </div>

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
          Run details will appear here when connected to an Intermediate or Full tier backend.
        </p>
      </FeatureGate>
    </div>
  );
}
