import { useQuery } from '@tanstack/react-query';
import { useSpine, useSpineClient } from '../../api';
import { SkeletonWidget } from '../../components';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export default function SettingsPage() {
  const { tier, capabilities, status } = useSpine();
  const client = useSpineClient();
  
  const isConnected = status === 'connected';
  const tierName = tier || 'basic';
  const apiVersion = capabilities?.api_version || '—';
  const hasApiKeys = tierName === 'intermediate' || tierName === 'full';
  
  // Fetch storage stats
  const { data: storageStats, isLoading: storageLoading, error: storageError } = useQuery({
    queryKey: ['spine', 'ops', 'storage'],
    queryFn: () => client.getStorageStats(),
    enabled: isConnected,
    staleTime: 30 * 1000, // 30 seconds
  });
  
  // Fetch captures list
  const { data: capturesData, isLoading: capturesLoading, error: capturesError } = useQuery({
    queryKey: ['spine', 'ops', 'captures'],
    queryFn: () => client.listCaptures(),
    enabled: isConnected,
    staleTime: 30 * 1000,
  });
  
  return (
    <div className="settings-page">
      <header className="page-header">
        <h1 className="page-title">Settings</h1>
      </header>

      <div className="settings-grid">
        {/* User Settings */}
        <section className="card">
          <header className="card-header">
            <h2>User Preferences</h2>
          </header>
          <div className="card-body">
            <div className="setting-row">
              <div className="setting-info">
                <label>Theme</label>
                <span className="setting-desc">Dashboard color theme</span>
              </div>
              <select className="setting-input">
                <option value="dark">Dark</option>
                <option value="light">Light</option>
              </select>
            </div>
            <div className="setting-row">
              <div className="setting-info">
                <label>Timezone</label>
                <span className="setting-desc">Display timezone for timestamps</span>
              </div>
              <select className="setting-input">
                <option value="America/New_York">America/New_York</option>
                <option value="UTC">UTC</option>
                <option value="America/Chicago">America/Chicago</option>
                <option value="America/Los_Angeles">America/Los_Angeles</option>
              </select>
            </div>
            <div className="setting-row">
              <div className="setting-info">
                <label>Auto-refresh</label>
                <span className="setting-desc">Automatically refresh dashboard data</span>
              </div>
              <label className="toggle">
                <input type="checkbox" defaultChecked />
                <span className="toggle-slider"></span>
              </label>
            </div>
          </div>
        </section>

        {/* System Settings */}
        <section className="card">
          <header className="card-header">
            <h2>System Settings</h2>
            <span className="card-badge">Admin Only</span>
          </header>
          <div className="card-body">
            <div className="setting-row">
              <div className="setting-info">
                <label>Data Retention</label>
                <span className="setting-desc">Days to retain historical data</span>
              </div>
              <input type="number" className="setting-input" defaultValue={90} />
            </div>
            <div className="setting-row">
              <div className="setting-info">
                <label>Alert Email</label>
                <span className="setting-desc">Email for critical alerts</span>
              </div>
              <input type="email" className="setting-input" placeholder="ops@company.com" />
            </div>
          </div>
        </section>

        {/* API Keys */}
        <section className="card">
          <header className="card-header">
            <h2>API Keys</h2>
            {!hasApiKeys && (
              <span className="card-badge" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-muted)' }}>
                Advanced Tier
              </span>
            )}
          </header>
          <div className="card-body">
            {hasApiKeys ? (
              <>
                <div className="api-key-list">
                  <div className="api-key-row">
                    <div className="key-info">
                      <span className="key-name">Production Key</span>
                      <code className="key-value">ms_prod_••••••••••••</code>
                    </div>
                    <button className="btn btn-sm">Rotate</button>
                  </div>
                  <div className="api-key-row">
                    <div className="key-info">
                      <span className="key-name">Development Key</span>
                      <code className="key-value">ms_dev_••••••••••••</code>
                    </div>
                    <button className="btn btn-sm">Rotate</button>
                  </div>
                </div>
                <button className="btn btn-primary">Generate New Key</button>
              </>
            ) : (
              <div style={{ 
                padding: '20px', 
                textAlign: 'center',
                color: 'var(--text-muted)',
                fontSize: '13px',
              }}>
                <div style={{ marginBottom: '8px' }}>
                  🔑 API key management requires Advanced tier
                </div>
                <div style={{ fontSize: '12px' }}>
                  Current tier: <code style={{ 
                    background: 'var(--bg-tertiary)', 
                    padding: '2px 6px', 
                    borderRadius: '3px' 
                  }}>{tierName}</code>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Storage Statistics */}
        <section className="card">
          <header className="card-header">
            <h2>Storage Statistics</h2>
          </header>
          <div className="card-body">
            {storageError ? (
              <div style={{ color: 'var(--accent-red)', fontSize: '13px' }}>
                Failed to load storage stats
              </div>
            ) : storageLoading ? (
              <SkeletonWidget type="stats" />
            ) : storageStats ? (
              <div className="about-info">
                <div className="about-row">
                  <label>Database Size</label>
                  <span style={{ fontFamily: 'monospace' }}>
                    {formatBytes(storageStats.database_size_bytes)}
                  </span>
                </div>
                <div className="about-row">
                  <label>Total Rows</label>
                  <span style={{ fontFamily: 'monospace' }}>
                    {storageStats.total_rows.toLocaleString()}
                  </span>
                </div>
                <div className="about-row">
                  <label>Tables</label>
                  <span style={{ fontFamily: 'monospace' }}>
                    {storageStats.tables.length}
                  </span>
                </div>
                {storageStats.tables.slice(0, 5).map((table) => (
                  <div key={table.name} className="about-row" style={{ paddingLeft: '16px' }}>
                    <label style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {table.name}
                    </label>
                    <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>
                      {table.row_count.toLocaleString()} rows
                    </span>
                  </div>
                ))}
                {storageStats.tables.length > 5 && (
                  <div style={{ 
                    fontSize: '11px', 
                    color: 'var(--text-muted)',
                    paddingLeft: '16px',
                    marginTop: '4px',
                  }}>
                    +{storageStats.tables.length - 5} more tables
                  </div>
                )}
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
                No storage data available
              </div>
            )}
          </div>
        </section>

        {/* Data Captures */}
        <section className="card">
          <header className="card-header">
            <h2>Data Captures</h2>
            {capturesData && (
              <span className="card-count">{capturesData.count}</span>
            )}
          </header>
          <div className="card-body">
            {capturesError ? (
              <div style={{ color: 'var(--accent-red)', fontSize: '13px' }}>
                Failed to load captures
              </div>
            ) : capturesLoading ? (
              <SkeletonWidget type="list" />
            ) : capturesData && capturesData.captures.length > 0 ? (
              <div style={{ maxHeight: '250px', overflowY: 'auto' }}>
                <table className="data-table" style={{ fontSize: '12px' }}>
                  <thead>
                    <tr>
                      <th>Week</th>
                      <th>Tier</th>
                      <th style={{ textAlign: 'right' }}>Rows</th>
                    </tr>
                  </thead>
                  <tbody>
                    {capturesData.captures.slice(0, 15).map((capture) => (
                      <tr key={capture.capture_id}>
                        <td style={{ fontFamily: 'monospace' }}>{capture.week_ending}</td>
                        <td>{capture.tier}</td>
                        <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>
                          {capture.row_count.toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {capturesData.captures.length > 15 && (
                  <div style={{ 
                    fontSize: '11px', 
                    color: 'var(--text-muted)',
                    padding: '8px',
                    textAlign: 'center',
                  }}>
                    +{capturesData.captures.length - 15} more captures
                  </div>
                )}
              </div>
            ) : (
              <div style={{ 
                color: 'var(--text-muted)', 
                fontSize: '13px',
                textAlign: 'center',
                padding: '20px',
              }}>
                No data captures yet. Run a pipeline to ingest data.
              </div>
            )}
          </div>
        </section>

        {/* About */}
        <section className="card">
          <header className="card-header">
            <h2>About</h2>
          </header>
          <div className="card-body">
            <div className="about-info">
              <div className="about-row">
                <label>API Version</label>
                <span style={{ fontFamily: 'monospace' }}>{apiVersion}</span>
              </div>
              <div className="about-row">
                <label>Tier</label>
                <span style={{ 
                  fontFamily: 'monospace',
                  textTransform: 'capitalize',
                }}>{tierName}</span>
              </div>
              <div className="about-row">
                <label>Connection</label>
                <span style={{ 
                  color: isConnected ? 'var(--accent-green)' : 'var(--accent-yellow)',
                }}>
                  {isConnected ? '● Connected' : '○ Connecting...'}
                </span>
              </div>
              <div className="about-row">
                <label>API Endpoint</label>
                <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>
                  {import.meta.env.VITE_MARKET_SPINE_URL || 'http://localhost:8000'}
                </span>
              </div>
              <div className="about-row">
                <label>Frontend Build</label>
                <span>{new Date().toISOString().split('T')[0]}</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
