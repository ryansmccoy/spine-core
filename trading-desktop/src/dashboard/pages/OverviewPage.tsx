import { useQuery } from '@tanstack/react-query';
import {
  CheckCircleIcon,
  ExclamationCircleIcon,
  ClockIcon,
  RectangleStackIcon,
  CircleStackIcon,
  CalendarDaysIcon,
} from '@heroicons/react/24/solid';
import { useSpine, useSpineClient, FeatureGate, TierUpgradeMessage } from '../../api';
import type { DataTier } from '../../api/spineTypes';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function daysSince(dateString: string): number {
  const date = new Date(dateString);
  const now = new Date();
  const diffTime = now.getTime() - date.getTime();
  return Math.floor(diffTime / (1000 * 60 * 60 * 24));
}

function formatRelativeDate(dateString: string): string {
  const days = daysSince(dateString);
  if (days === 0) return 'Today';
  if (days === 1) return '1 day ago';
  return `${days} days ago`;
}

export default function OverviewPage() {
  const { status, tier, capabilities, health } = useSpine();
  const client = useSpineClient();

  // Fetch pipeline count
  const { data: pipelinesData } = useQuery({
    queryKey: ['spine', 'pipelines'],
    queryFn: () => client.listPipelines(),
    enabled: status === 'connected',
  });

  // Fetch available weeks (as a proxy for data status)
  const { data: otcWeeks } = useQuery({
    queryKey: ['spine', 'data', 'weeks', 'OTC'],
    queryFn: () => client.queryWeeks('OTC', 5),
    enabled: status === 'connected',
  });
  
  const { data: nms1Weeks } = useQuery({
    queryKey: ['spine', 'data', 'weeks', 'NMS_TIER_1'],
    queryFn: () => client.queryWeeks('NMS_TIER_1', 5),
    enabled: status === 'connected',
  });
  
  const { data: nms2Weeks } = useQuery({
    queryKey: ['spine', 'data', 'weeks', 'NMS_TIER_2'],
    queryFn: () => client.queryWeeks('NMS_TIER_2', 5),
    enabled: status === 'connected',
  });
  
  // Fetch storage stats
  const { data: storageStats } = useQuery({
    queryKey: ['spine', 'ops', 'storage'],
    queryFn: () => client.getStorageStats(),
    enabled: status === 'connected',
    staleTime: 60 * 1000, // 1 minute
  });

  const pipelineCount = pipelinesData?.count ?? 0;
  const weeksCount = (otcWeeks?.count ?? 0) + (nms1Weeks?.count ?? 0) + (nms2Weeks?.count ?? 0);
  const dbSize = storageStats ? formatBytes(storageStats.database_size_bytes) : '—';
  
  // Data freshness info for all tiers
  const tierFreshness: Array<{ tier: DataTier; label: string; latestWeek: string | null; daysOld: number | null }> = [
    {
      tier: 'OTC',
      label: 'OTC (Non-ATS)',
      latestWeek: otcWeeks?.weeks?.[0]?.week_ending ?? null,
      daysOld: otcWeeks?.weeks?.[0]?.week_ending ? daysSince(otcWeeks.weeks[0].week_ending) : null,
    },
    {
      tier: 'NMS_TIER_1',
      label: 'NMS Tier 1',
      latestWeek: nms1Weeks?.weeks?.[0]?.week_ending ?? null,
      daysOld: nms1Weeks?.weeks?.[0]?.week_ending ? daysSince(nms1Weeks.weeks[0].week_ending) : null,
    },
    {
      tier: 'NMS_TIER_2',
      label: 'NMS Tier 2',
      latestWeek: nms2Weeks?.weeks?.[0]?.week_ending ?? null,
      daysOld: nms2Weeks?.weeks?.[0]?.week_ending ? daysSince(nms2Weeks.weeks[0].week_ending) : null,
    },
  ];
  
  // Determine if any data is stale (> 14 days old)
  const hasStaleData = tierFreshness.some(t => t.daysOld !== null && t.daysOld > 14);
  const hasNoData = tierFreshness.every(t => t.latestWeek === null);

  return (
    <div className="overview-page">
      <header className="page-header">
        <h1 className="page-title">
          Overview
          {tier && (
            <span className="page-subtitle">
              — {tier.charAt(0).toUpperCase() + tier.slice(1)} Tier
            </span>
          )}
        </h1>
      </header>

      {/* System Status Banner */}
      <SystemStatusBanner 
        status={status} 
        health={health} 
        capabilities={capabilities}
        hasStaleData={hasStaleData}
        hasNoData={hasNoData}
      />

      {/* Stats Grid */}
      <div className="stats-grid">
        <StatCard
          title="Pipelines"
          value={pipelineCount}
          icon={RectangleStackIcon}
          color="blue"
        />
        <StatCard
          title="Data Weeks"
          value={weeksCount}
          icon={CalendarDaysIcon}
          color="green"
        />
        <StatCard
          title="Database Size"
          value={dbSize}
          icon={CircleStackIcon}
          color="purple"
        />
        <FeatureGate 
          feature="hasExecutionHistory" 
          fallback={
            <StatCard
              title="Execution History"
              value="—"
              icon={ClockIcon}
              color="gray"
              note="Requires Intermediate"
            />
          }
        >
          <StatCard
            title="Success Rate (24h)"
            value="—"
            icon={CheckCircleIcon}
            color="green"
          />
        </FeatureGate>
      </div>
      
      {/* Data Freshness Card */}
      <section className="card data-freshness-card">
        <header className="card-header">
          <h2>Data Freshness</h2>
          {hasStaleData && (
            <span className="freshness-warning">⚠️ Some data may be stale</span>
          )}
        </header>
        <div className="card-body">
          {hasNoData ? (
            <div className="empty-state">
              <p>No data ingested yet. Run a pipeline to load FINRA OTC data.</p>
            </div>
          ) : (
            <div className="freshness-grid">
              {tierFreshness.map(({ tier, label, latestWeek, daysOld }) => (
                <FreshnessRow
                  key={tier}
                  label={label}
                  latestWeek={latestWeek}
                  daysOld={daysOld}
                />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Two-column layout */}
      <div className="overview-grid">
        {/* Pipelines Summary */}
        <section className="card">
          <header className="card-header">
            <h2>Available Pipelines</h2>
            <span className="card-count">{pipelineCount}</span>
          </header>
          <div className="card-body">
            {pipelinesData?.pipelines && pipelinesData.pipelines.length > 0 ? (
              <ul className="pipeline-list">
                {pipelinesData.pipelines.slice(0, 5).map((p) => (
                  <li key={p.name} className="pipeline-row">
                    <span className="pipeline-name">{p.name}</span>
                    <span className="pipeline-desc">{p.description}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="empty-state">
                <p>No pipelines registered</p>
              </div>
            )}
          </div>
        </section>

        {/* Tier Capabilities */}
        <section className="card">
          <header className="card-header">
            <h2>Tier Capabilities</h2>
          </header>
          <div className="card-body">
            <CapabilitiesTable />
          </div>
        </section>

        {/* Queue Overview - gated */}
        <FeatureGate 
          feature="hasQueues" 
          fallback={
            <section className="card">
              <header className="card-header">
                <h2>Queue Depths</h2>
              </header>
              <div className="card-body">
                <TierUpgradeMessage feature="Queue Management" requiredTier="intermediate" />
              </div>
            </section>
          }
        >
          <section className="card">
            <header className="card-header">
              <h2>Queue Depths</h2>
            </header>
            <div className="card-body">
              <p>Queue data available in intermediate tier</p>
            </div>
          </section>
        </FeatureGate>

        {/* Recent Failures - gated */}
        <FeatureGate 
          feature="hasExecutionHistory" 
          fallback={
            <section className="card">
              <header className="card-header">
                <h2>Recent Failures</h2>
              </header>
              <div className="card-body">
                <TierUpgradeMessage feature="Execution History" requiredTier="intermediate" />
              </div>
            </section>
          }
        >
          <section className="card">
            <header className="card-header">
              <h2>Recent Failures</h2>
            </header>
            <div className="card-body">
              <p>Failure history available in intermediate tier</p>
            </div>
          </section>
        </FeatureGate>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────

interface StatusBannerProps {
  status: string;
  health: { status: string; timestamp: string } | null;
  capabilities: { tier: string; version: string } | null;
  hasStaleData: boolean;
  hasNoData: boolean;
}

function SystemStatusBanner({ status, health, capabilities, hasStaleData, hasNoData }: StatusBannerProps) {
  if (status === 'connecting') {
    return (
      <div className="status-banner status-loading">
        <div className="spinner" /> Connecting to backend...
      </div>
    );
  }

  if (status === 'error' || status === 'disconnected') {
    return (
      <div className="status-banner status-degraded">
        <div className="status-icon">
          <ExclamationCircleIcon className="icon-degraded" />
        </div>
        <div className="status-text">
          <strong>Backend Unavailable</strong>
          <span className="status-hint">Check that the Market Spine API is running</span>
        </div>
      </div>
    );
  }

  const isHealthy = health?.status === 'ok';
  
  // Determine overall system status
  // Priority: backend health > stale data > no data
  let statusLevel: 'healthy' | 'warning' | 'degraded' = 'healthy';
  let statusText = 'All Systems Operational';
  let statusHint = '';
  
  if (!isHealthy) {
    statusLevel = 'degraded';
    statusText = 'System Degraded';
    statusHint = 'Backend reported unhealthy status';
  } else if (hasStaleData) {
    statusLevel = 'warning';
    statusText = 'Data May Be Stale';
    statusHint = 'Some data tiers haven\'t been updated recently';
  } else if (hasNoData) {
    statusLevel = 'warning';
    statusText = 'No Data Yet';
    statusHint = 'Run a pipeline to ingest data';
  }

  const bannerClass = statusLevel === 'healthy' ? 'status-healthy' : 
                      statusLevel === 'warning' ? 'status-warning' : 'status-degraded';
  
  const IconComponent = statusLevel === 'healthy' ? CheckCircleIcon : 
                        statusLevel === 'warning' ? ExclamationCircleIcon : ExclamationCircleIcon;
  const iconClass = statusLevel === 'healthy' ? 'icon-healthy' : 
                    statusLevel === 'warning' ? 'icon-warning' : 'icon-degraded';

  return (
    <div className={`status-banner ${bannerClass}`}>
      <div className="status-icon">
        <IconComponent className={iconClass} />
      </div>
      <div className="status-text">
        <strong>{statusText}</strong>
        {statusHint && <span className="status-hint">{statusHint}</span>}
        <span className="status-services">
          {capabilities && (
            <span className="service-badge healthy">
              {capabilities.tier} v{capabilities.version}
            </span>
          )}
        </span>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  icon: Icon,
  color,
  note,
}: {
  title: string;
  value: string | number;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  note?: string;
}) {
  return (
    <div className={`stat-card stat-${color}`}>
      <div className="stat-icon">
        <Icon className="icon" />
      </div>
      <div className="stat-content">
        <span className="stat-value">{value}</span>
        <span className="stat-title">{title}</span>
        {note && <span className="stat-note">{note}</span>}
      </div>
    </div>
  );
}

function CapabilitiesTable() {
  const { capabilities } = useSpine();

  if (!capabilities) {
    return <div className="spinner" />;
  }

  const features = [
    { name: 'Sync Execution', available: capabilities.sync_execution },
    { name: 'Async Execution', available: capabilities.async_execution },
    { name: 'Execution History', available: capabilities.execution_history },
    { name: 'Scheduling', available: capabilities.scheduling },
    { name: 'Authentication', available: capabilities.authentication },
    { name: 'Rate Limiting', available: capabilities.rate_limiting },
    { name: 'Webhooks', available: capabilities.webhook_notifications },
  ];

  return (
    <table className="capabilities-table">
      <tbody>
        {features.map((f) => (
          <tr key={f.name}>
            <td>{f.name}</td>
            <td>
              {f.available ? (
                <CheckCircleIcon className="cap-icon available" />
              ) : (
                <span className="cap-unavailable">—</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FreshnessRow({
  label,
  latestWeek,
  daysOld,
}: {
  label: string;
  latestWeek: string | null;
  daysOld: number | null;
}) {
  if (!latestWeek) {
    return (
      <div className="freshness-row freshness-empty">
        <span className="freshness-label">{label}</span>
        <span className="freshness-status">No data</span>
        <span className="freshness-indicator">—</span>
      </div>
    );
  }
  
  // Determine freshness status
  // Fresh: < 7 days, Warning: 7-14 days, Stale: > 14 days
  let statusClass = 'freshness-fresh';
  let indicator = '✓';
  if (daysOld !== null) {
    if (daysOld > 14) {
      statusClass = 'freshness-stale';
      indicator = '⚠️';
    } else if (daysOld > 7) {
      statusClass = 'freshness-warning';
      indicator = '⚠';
    }
  }
  
  return (
    <div className={`freshness-row ${statusClass}`}>
      <span className="freshness-label">{label}</span>
      <span className="freshness-week">Week of {latestWeek}</span>
      <span className="freshness-age">{formatRelativeDate(latestWeek)}</span>
      <span className="freshness-indicator">{indicator}</span>
    </div>
  );
}
