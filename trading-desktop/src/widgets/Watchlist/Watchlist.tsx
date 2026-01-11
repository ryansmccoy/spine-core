/**
 * Watchlist Widget
 * 
 * Quick access to tracked symbols
 */

import { useAppStore } from '../../store';

export function Watchlist() {
  const { watchlist, activeSymbol, setActiveSymbol, removeFromWatchlist } = useAppStore();
  
  return (
    <div className="widget-panel">
      <div className="widget-header">Watchlist</div>
      <div className="widget-body" style={{ padding: 0 }}>
        {watchlist.length === 0 ? (
          <div style={{ padding: '12px', color: 'var(--text-muted)' }}>
            No symbols in watchlist
          </div>
        ) : (
          <div>
            {watchlist.map((symbol) => (
              <div
                key={symbol}
                onClick={() => setActiveSymbol(symbol)}
                style={{
                  padding: '10px 12px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--border-color)',
                  backgroundColor:
                    symbol === activeSymbol ? 'var(--bg-tertiary)' : 'transparent',
                }}
              >
                <span
                  style={{
                    fontWeight: symbol === activeSymbol ? 700 : 500,
                    color:
                      symbol === activeSymbol
                        ? 'var(--accent-blue)'
                        : 'var(--text-primary)',
                  }}
                >
                  {symbol}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFromWatchlist(symbol);
                  }}
                  style={{
                    padding: '2px 6px',
                    fontSize: '10px',
                    opacity: 0.5,
                  }}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default Watchlist;
