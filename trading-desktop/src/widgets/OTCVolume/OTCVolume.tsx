/**
 * OTC Volume Widget
 * 
 * Shows weekly OTC transparency data from the FINRA Basic tier endpoints.
 * Uses spineClient for data fetching.
 */

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useAppStore } from '../../store';
import { useSpineClient, useSpine } from '../../api';
import type { OTCWeeklyData } from '../../api';
import { SkeletonWidget } from '../../components';

function formatNumber(n: number): string {
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + 'B';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return n.toString();
}

function formatPercent(n: number | null): string {
  if (n === null || n === undefined) return '—';
  const sign = n >= 0 ? '+' : '';
  return sign + (n * 100).toFixed(1) + '%';
}

export function OTCVolume() {
  const { activeSymbol, setActiveSymbol } = useAppStore();
  const { status } = useSpine();
  const client = useSpineClient();
  
  // Fetch top OTC symbols
  const { data: topVolume, isLoading: loadingTop, error: topError } = useQuery({
    queryKey: ['spine', 'otc', 'top-volume'],
    queryFn: () => client.getTopOTCSymbols(15, 'OTC'),
    enabled: status === 'connected',
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Fetch data for selected symbol (if any)
  const { data: symbolData, isLoading: loadingSymbol } = useQuery({
    queryKey: ['spine', 'otc', 'symbol', activeSymbol],
    queryFn: () => client.getSymbolOTCData(activeSymbol!, 'OTC'),
    enabled: status === 'connected' && !!activeSymbol,
    staleTime: 5 * 60 * 1000,
  });
  
  const isConnected = status === 'connected';
  
  return (
    <div className="widget-panel">
      <div className="widget-header">
        OTC Weekly Volume {activeSymbol && `— ${activeSymbol}`}
      </div>
      <div className="widget-body">
        {/* Connection warning */}
        {!isConnected && (
          <div style={{ 
            padding: '12px', 
            background: 'rgba(234, 179, 8, 0.1)', 
            borderRadius: '4px',
            marginBottom: '12px',
            color: 'var(--accent-yellow)',
            fontSize: '12px',
          }}>
            Connecting to Market Spine...
          </div>
        )}

        {/* Selected Symbol Info */}
        {activeSymbol && (
          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ margin: '0 0 8px', fontSize: '12px', color: 'var(--text-muted)' }}>
              Symbol Data (Latest Week)
            </h4>
            {loadingSymbol ? (
              <SkeletonWidget type="stats" />
            ) : symbolData ? (
              <div style={{ 
                padding: '12px', 
                background: 'var(--bg-secondary)', 
                borderRadius: '4px' 
              }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                  <div>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Week</div>
                    <div style={{ fontFamily: 'monospace' }}>{symbolData.week_ending}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Volume</div>
                    <div style={{ fontFamily: 'monospace' }}>{formatNumber(symbolData.total_volume)}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Rank</div>
                    <div style={{ fontFamily: 'monospace' }}>#{symbolData.rank}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>WoW Change</div>
                    <div style={{ fontFamily: 'monospace' }}>{formatPercent(symbolData.wow_change)}</div>
                  </div>
                </div>
                <div style={{ 
                  marginTop: '8px', 
                  paddingTop: '8px', 
                  borderTop: '1px solid var(--border-color)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    💡 View detailed history
                  </span>
                  <Link 
                    to={`/dashboard/data?symbol=${activeSymbol}`}
                    style={{
                      fontSize: '11px',
                      padding: '4px 8px',
                      background: 'var(--accent-blue)',
                      color: 'white',
                      borderRadius: '4px',
                      textDecoration: 'none',
                    }}
                  >
                    View History →
                  </Link>
                </div>
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                No OTC data for {activeSymbol}
              </div>
            )}
          </div>
        )}
        
        {/* Top Volume */}
        <div>
          <h4 style={{ margin: '0 0 8px', fontSize: '12px', color: 'var(--text-muted)' }}>
            Top OTC Volume (Latest Week)
          </h4>
          {topError ? (
            <div style={{ color: 'var(--accent-red)', fontSize: '12px' }}>
              {topError instanceof Error ? topError.message : 'Failed to load data'}
            </div>
          ) : loadingTop ? (
            <SkeletonWidget type="list" />
          ) : topVolume && topVolume.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Symbol</th>
                  <th style={{ textAlign: 'right' }}>Shares</th>
                  <th style={{ textAlign: 'right' }}>WoW</th>
                </tr>
              </thead>
              <tbody>
                {topVolume.map((row: OTCWeeklyData) => (
                  <tr
                    key={row.symbol}
                    onClick={() => setActiveSymbol(row.symbol)}
                    style={{ cursor: 'pointer' }}
                    className={row.symbol === activeSymbol ? 'row-selected' : ''}
                  >
                    <td>{row.rank}</td>
                    <td style={{ fontWeight: row.symbol === activeSymbol ? 700 : 400 }}>
                      {row.symbol}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>
                      {formatNumber(row.total_volume)}
                    </td>
                    <td
                      style={{ textAlign: 'right', fontFamily: 'monospace' }}
                      className={
                        row.wow_change !== null && row.wow_change > 0
                          ? 'price-up'
                          : row.wow_change !== null && row.wow_change < 0
                          ? 'price-down'
                          : ''
                      }
                    >
                      {formatPercent(row.wow_change)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ 
              color: 'var(--text-muted)', 
              fontSize: '12px',
              textAlign: 'center',
              padding: '20px',
            }}>
              <div style={{ marginBottom: '8px' }}>No OTC data available</div>
              <div style={{ fontSize: '11px' }}>
                Run the <code>finra.otc_transparency.ingest_week</code> pipeline to load data
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default OTCVolume;
