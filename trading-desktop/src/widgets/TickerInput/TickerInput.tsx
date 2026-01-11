/**
 * TickerInput Widget
 *
 * Controls the active symbol for context linking.
 * Note: Symbol autocomplete requires a symbol master endpoint (future enhancement).
 */

import { useState, useCallback } from 'react';
import type { KeyboardEvent } from 'react';
import { useAppStore } from '../../store';

export function TickerInput() {
  const { activeSymbol, setActiveSymbol } = useAppStore();
  const [inputValue, setInputValue] = useState(activeSymbol || '');

  const handleSubmit = useCallback(() => {
    if (inputValue.trim()) {
      setActiveSymbol(inputValue.trim().toUpperCase());
    }
  }, [inputValue, setActiveSymbol]);

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSubmit();
    }
  };

  return (
    <div className="widget-panel">
      <div className="widget-header">Symbol Search</div>
      <div className="widget-body">
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value.toUpperCase())}
            onKeyDown={handleKeyDown}
            placeholder="Enter symbol (e.g., AAPL)..."
            style={{ flex: 1, fontWeight: 600, fontSize: '16px' }}
          />
          <button onClick={handleSubmit}>Go</button>
        </div>

        {activeSymbol && (
          <div style={{ marginTop: '16px', color: 'var(--text-muted)' }}>
            Active:{' '}
            <span style={{ color: 'var(--accent-blue)', fontWeight: 600 }}>
              {activeSymbol}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export default TickerInput;
