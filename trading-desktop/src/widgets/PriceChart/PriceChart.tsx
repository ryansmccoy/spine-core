/**
 * PriceChart Widget
 * 
 * Displays candlestick chart using Lightweight Charts.
 * 
 * NOTE: Price data requires the Intermediate tier (external market data feeds).
 * In Basic tier, this widget shows a placeholder message.
 * 
 * Once data is available via Alpha Vantage integration, the chart renders
 * actual OHLCV data from GET /v1/data/prices/{symbol}.
 */

import { useQuery } from '@tanstack/react-query';
import { useSpine, useSpineClient } from '../../api';
import { useAppStore } from '../../store';
import type { PriceCandle } from '../../api/spineTypes';

export function PriceChart() {
  const { activeSymbol } = useAppStore();
  const { tier, status } = useSpine();
  const client = useSpineClient();
  
  const isConnected = status === 'connected';
  const tierName = tier || 'basic';
  const hasPriceData = tierName === 'intermediate' || tierName === 'full';
  
  // Fetch price data when we have a symbol and the tier supports it
  const { data: priceData, isLoading, error } = useQuery({
    queryKey: ['spine', 'prices', activeSymbol],
    queryFn: () => client.getPrices(activeSymbol!, 60),
    enabled: isConnected && hasPriceData && !!activeSymbol,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
  });
  
  return (
    <div className="widget-panel">
      <div className="widget-header">
        Chart {activeSymbol && `— ${activeSymbol}`}
        {hasPriceData && priceData && priceData.count > 0 && (
          <span style={{ 
            marginLeft: '8px', 
            fontSize: '11px', 
            color: 'var(--text-muted)' 
          }}>
            ({priceData.count} days)
          </span>
        )}
      </div>
      <div className="widget-body" style={{ padding: 0, position: 'relative', minHeight: '300px' }}>
        {/* Connection warning */}
        {!isConnected && (
          <div style={{ 
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--bg-primary)',
          }}>
            <div style={{ 
              padding: '12px', 
              background: 'rgba(234, 179, 8, 0.1)', 
              borderRadius: '4px',
              color: 'var(--accent-yellow)',
              fontSize: '12px',
            }}>
              Connecting to Market Spine...
            </div>
          </div>
        )}
        
        {isConnected && !hasPriceData && (
          <div style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            textAlign: 'center',
            color: 'var(--text-muted)',
          }}>
            <div>
              <div style={{ 
                fontSize: '48px', 
                marginBottom: '16px',
                opacity: 0.4,
              }}>
                📈
              </div>
              <div style={{ 
                fontSize: '14px', 
                fontWeight: 600,
                marginBottom: '8px',
                color: 'var(--text-primary)',
              }}>
                Price Charts — Intermediate Tier
              </div>
              <div style={{ fontSize: '12px', lineHeight: 1.5, maxWidth: '280px' }}>
                Historical OHLCV price data requires external market data feeds
                available starting in the <strong>Intermediate</strong> tier.
              </div>
              <div style={{ 
                marginTop: '16px',
                padding: '8px 12px',
                background: 'var(--bg-tertiary)',
                borderRadius: '4px',
                fontSize: '11px',
              }}>
                Current tier: <code style={{ 
                  background: 'var(--bg-secondary)', 
                  padding: '2px 6px', 
                  borderRadius: '3px' 
                }}>{tierName}</code>
              </div>
            </div>
          </div>
        )}
        
        {isConnected && hasPriceData && !activeSymbol && (
          <div style={{ 
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-muted)',
            fontSize: '12px',
          }}>
            Select a symbol to view chart
          </div>
        )}
        
        {isConnected && hasPriceData && activeSymbol && isLoading && (
          <div style={{ 
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-muted)',
            fontSize: '12px',
          }}>
            <div className="spinner" style={{ marginRight: '8px' }} />
            Loading chart for {activeSymbol}...
          </div>
        )}
        
        {isConnected && hasPriceData && activeSymbol && error && (
          <div style={{ 
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent-red)',
            fontSize: '12px',
            padding: '24px',
            textAlign: 'center',
          }}>
            Failed to load price data for {activeSymbol}
          </div>
        )}
        
        {isConnected && hasPriceData && activeSymbol && !isLoading && !error && priceData && (
          <PriceChartContent candles={priceData.candles} symbol={activeSymbol} />
        )}
      </div>
    </div>
  );
}

/**
 * Render price data as a simple table (placeholder until Lightweight Charts is added)
 */
function PriceChartContent({ candles, symbol }: { candles: PriceCandle[]; symbol: string }) {
  if (candles.length === 0) {
    return (
      <div style={{ 
        position: 'absolute',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
        textAlign: 'center',
        color: 'var(--text-muted)',
      }}>
        <div>
          <div style={{ fontSize: '14px', marginBottom: '8px' }}>
            No price data available for {symbol}
          </div>
          <div style={{ fontSize: '12px' }}>
            Run the price ingestion pipeline to fetch data from Alpha Vantage.
          </div>
        </div>
      </div>
    );
  }
  
  // Get the most recent candle for summary
  const latest = candles[0];
  const oldest = candles[candles.length - 1];
  
  // Calculate price range for the period
  const high = Math.max(...candles.map(c => c.high));
  const low = Math.min(...candles.map(c => c.low));
  const change = latest.close - oldest.close;
  const changePercent = (change / oldest.close) * 100;
  
  return (
    <div style={{ 
      padding: '16px', 
      height: '100%', 
      display: 'flex', 
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {/* Price summary */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: '12px',
        marginBottom: '16px',
        padding: '12px',
        background: 'var(--bg-tertiary)',
        borderRadius: '6px',
      }}>
        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px' }}>
            Latest Close
          </div>
          <div style={{ fontSize: '16px', fontWeight: 600 }}>
            ${latest.close.toFixed(2)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px' }}>
            Period Change
          </div>
          <div style={{ 
            fontSize: '14px', 
            fontWeight: 600,
            color: change >= 0 ? 'var(--accent-green)' : 'var(--accent-red)',
          }}>
            {change >= 0 ? '+' : ''}{changePercent.toFixed(2)}%
          </div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px' }}>
            Period High
          </div>
          <div style={{ fontSize: '14px' }}>
            ${high.toFixed(2)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px' }}>
            Period Low
          </div>
          <div style={{ fontSize: '14px' }}>
            ${low.toFixed(2)}
          </div>
        </div>
      </div>
      
      {/* Recent prices table */}
      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '8px' }}>
        Recent {Math.min(candles.length, 10)} days
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>
        <table style={{ 
          width: '100%', 
          fontSize: '11px',
          borderCollapse: 'collapse',
        }}>
          <thead>
            <tr style={{ 
              borderBottom: '1px solid var(--border-color)',
              color: 'var(--text-muted)',
            }}>
              <th style={{ textAlign: 'left', padding: '6px 8px' }}>Date</th>
              <th style={{ textAlign: 'right', padding: '6px 8px' }}>Open</th>
              <th style={{ textAlign: 'right', padding: '6px 8px' }}>High</th>
              <th style={{ textAlign: 'right', padding: '6px 8px' }}>Low</th>
              <th style={{ textAlign: 'right', padding: '6px 8px' }}>Close</th>
              <th style={{ textAlign: 'right', padding: '6px 8px' }}>Volume</th>
            </tr>
          </thead>
          <tbody>
            {candles.slice(0, 10).map((candle) => (
              <tr 
                key={candle.date}
                style={{ borderBottom: '1px solid var(--border-color)' }}
              >
                <td style={{ padding: '6px 8px' }}>{candle.date}</td>
                <td style={{ textAlign: 'right', padding: '6px 8px' }}>${candle.open.toFixed(2)}</td>
                <td style={{ textAlign: 'right', padding: '6px 8px' }}>${candle.high.toFixed(2)}</td>
                <td style={{ textAlign: 'right', padding: '6px 8px' }}>${candle.low.toFixed(2)}</td>
                <td style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 500 }}>
                  ${candle.close.toFixed(2)}
                </td>
                <td style={{ textAlign: 'right', padding: '6px 8px', color: 'var(--text-muted)' }}>
                  {formatVolume(candle.volume)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatVolume(volume: number): string {
  if (volume >= 1_000_000_000) return (volume / 1_000_000_000).toFixed(1) + 'B';
  if (volume >= 1_000_000) return (volume / 1_000_000).toFixed(1) + 'M';
  if (volume >= 1_000) return (volume / 1_000).toFixed(1) + 'K';
  return volume.toString();
}

export default PriceChart;
