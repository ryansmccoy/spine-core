import { TierUpgradeMessage, FeatureGate } from '../../api';

export default function IncidentsPage() {
  return (
    <div className="incidents-page">
      <header className="page-header">
        <h1 className="page-title">Incidents</h1>
      </header>

      <FeatureGate
        feature="hasIncidents"
        fallback={
          <TierUpgradeMessage 
            feature="Incident Management" 
            requiredTier="full" 
          />
        }
      >
        <p>Incident management would appear here</p>
      </FeatureGate>
    </div>
  );
}
