import { NavLink, Outlet, Link } from 'react-router-dom';
import {
  HomeIcon,
  RectangleStackIcon,
  QueueListIcon,
  CircleStackIcon,
  ServerStackIcon,
  ExclamationTriangleIcon,
  Cog6ToothIcon,
  ArrowPathIcon,
  ClockIcon,
  BeakerIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import { useTemporalContext } from './hooks/useTemporalContext';
import { useSpine } from '../api';
import { ErrorBoundary } from '../components';

const navigation = [
  { name: 'Overview', href: '/dashboard', icon: HomeIcon, end: true },
  { name: 'Pipelines', href: '/dashboard/pipelines', icon: RectangleStackIcon },
  { name: 'Jobs', href: '/dashboard/jobs', icon: QueueListIcon, feature: 'hasExecutionHistory' as const },
  { name: 'Queues', href: '/dashboard/queues', icon: ServerStackIcon, feature: 'hasQueues' as const },
  { name: 'Data Assets', href: '/dashboard/data', icon: CircleStackIcon },
  { name: 'Orchestrator Lab', href: '/dashboard/orchestrator', icon: BeakerIcon, feature: 'hasOrchestratorLab' as const },
  { name: 'Incidents', href: '/dashboard/incidents', icon: ExclamationTriangleIcon, feature: 'hasIncidents' as const },
  { name: 'Settings', href: '/dashboard/settings', icon: Cog6ToothIcon },
];

function ConnectionBanner() {
  const { status, tier, capabilities, error, reconnect } = useSpine();

  if (status === 'connected') {
    return (
      <div className="connection-banner connection-connected">
        <CheckCircleIcon className="connection-icon" />
        <span className="connection-tier">{tier?.toUpperCase()}</span>
        <span className="connection-version">v{capabilities?.version}</span>
      </div>
    );
  }

  if (status === 'connecting') {
    return (
      <div className="connection-banner connection-connecting">
        <ArrowPathIcon className="connection-icon animate-spin" />
        <span>Connecting to backend...</span>
      </div>
    );
  }

  return (
    <div className="connection-banner connection-error">
      {status === 'error' ? (
        <XCircleIcon className="connection-icon" />
      ) : (
        <ExclamationCircleIcon className="connection-icon" />
      )}
      <span>{error?.message ?? 'Connection lost'}</span>
      <button onClick={reconnect} className="reconnect-btn">
        Reconnect
      </button>
    </div>
  );
}

export default function DashboardLayout() {
  const { mode, asOf, setMode, refresh, lastRefresh } = useTemporalContext();
  const { capabilities } = useSpine();

  return (
    <div className="dashboard-layout">
      {/* Connection Status Banner */}
      <ConnectionBanner />
      
      {/* Sidebar */}
      <aside className="dashboard-sidebar">
        <div className="sidebar-header">
          <Link to="/dashboard" className="logo">
            <span className="logo-icon">◈</span>
            <span className="logo-text">Market Spine</span>
          </Link>
          <span className="logo-subtitle">Control Plane</span>
        </div>

        <nav className="sidebar-nav">
          {navigation.map((item) => {
            // Check if this nav item requires a specific feature
            if (item.feature && capabilities && !capabilities[item.feature]) {
              return null; // Hide items that require unavailable features
            }
            return (
              <NavLink
                key={item.name}
                to={item.href}
                end={item.end}
                className={({ isActive }) =>
                  `nav-item ${isActive ? 'nav-item-active' : ''}`
                }
              >
                <item.icon className="nav-icon" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <Link to="/trading" className="nav-item trading-link">
            <span className="nav-icon">📊</span>
            <span>Trading Desktop</span>
          </Link>
        </div>
      </aside>

      {/* Main content area */}
      <div className="dashboard-main">
        {/* Temporal Context Bar */}
        <header className="temporal-bar">
          <div className="temporal-mode">
            <ClockIcon className="temporal-icon" />
            <span className="temporal-label">VIEWING:</span>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as 'live' | 'as_of')}
              className="temporal-select"
            >
              <option value="live">Live</option>
              <option value="as_of">Historical</option>
            </select>
            {mode === 'as_of' && (
              <input
                type="datetime-local"
                value={asOf?.slice(0, 16) || ''}
                className="temporal-input"
              />
            )}
          </div>

          {mode === 'as_of' && (
            <div className="temporal-warning">
              ⚠️ Viewing historical snapshot. Actions disabled.
            </div>
          )}

          <div className="temporal-refresh">
            <span className="refresh-time">
              Updated: {lastRefresh.toLocaleTimeString()}
            </span>
            <button onClick={refresh} className="refresh-btn" title="Refresh data">
              <ArrowPathIcon className="refresh-icon" />
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="dashboard-content">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
