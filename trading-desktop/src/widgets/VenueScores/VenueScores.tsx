/**
 * VenueScores Widget
 * 
 * Shows venue quality scores for order routing.
 * 
 * NOTE: Venue scoring requires the Advanced tier (external market data feeds).
 * In Basic tier, this widget shows a placeholder message.
 */

import { useSpine } from '../../api';

export function VenueScores() {
  const { tier, status } = useSpine();
  
  const isConnected = status === 'connected';
  const tierName = tier || 'basic';
  const hasVenueData = tierName === 'full';
  
  return (
    <div className="widget-panel">
      <div className="widget-header">
        Venue Quality Scores
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
        
        {isConnected && !hasVenueData && (
          <div style={{
            padding: '24px',
            textAlign: 'center',
            color: 'var(--text-muted)',
          }}>
            <div style={{ 
              fontSize: '32px', 
              marginBottom: '12px',
              opacity: 0.5,
            }}>
              🏛️
            </div>
            <div style={{ 
              fontSize: '14px', 
              fontWeight: 600,
              marginBottom: '8px',
              color: 'var(--text-primary)',
            }}>
              Venue Scores — Advanced Tier
            </div>
            <div style={{ fontSize: '12px', lineHeight: 1.5 }}>
              Real-time venue quality scoring requires external market data feeds
              available in the <strong>Advanced</strong> tier.
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
        )}
        
        {isConnected && hasVenueData && (
          <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
            {/* When Advanced tier is connected, venue data would be fetched here */}
            Venue scoring enabled — data loading...
          </div>
        )}
      </div>
    </div>
  );
}

export default VenueScores;
