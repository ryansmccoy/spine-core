import { TierUpgradeMessage, FeatureGate } from '../../api';

export default function QueuesPage() {
  return (
    <div className="queues-page">
      <header className="page-header">
        <h1 className="page-title">Queues</h1>
      </header>

      <FeatureGate
        feature="hasQueues"
        fallback={
          <TierUpgradeMessage 
            feature="Queue Management" 
            requiredTier="intermediate" 
          />
        }
      >
        <p>Queue management would appear here</p>
      </FeatureGate>
    </div>
  );
}
