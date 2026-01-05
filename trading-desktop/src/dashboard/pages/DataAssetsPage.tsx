import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { useSpineClient } from '../../api';
import type { DataTier, WeekInfo, SymbolInfo, SymbolWeekData } from '../../api';
import { SkeletonWidget, NoDataEmptyState } from '../../components';

const TIERS: { value: DataTier; label: string }[] = [
  { value: 'OTC', label: 'OTC (Non-Exchange)' },
  { value: 'NMS_TIER_1', label: 'NMS Tier 1 (NYSE, NASDAQ)' },
  { value: 'NMS_TIER_2', label: 'NMS Tier 2 (Other NMS)' },
];

export default function DataAssetsPage() {
  const client = useSpineClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedTier, setSelectedTier] = useState<DataTier>('OTC');
  const [selectedWeek, setSelectedWeek] = useState<string | null>(null);
  const [symbolLimit, setSymbolLimit] = useState(25);
  
  // Read symbol from URL params
  const symbolFromUrl = searchParams.get('symbol');
  const [focusedSymbol, setFocusedSymbol] = useState<string | null>(symbolFromUrl);
  
  // Sync focusedSymbol with URL
  useEffect(() => {
    if (symbolFromUrl) {
      setFocusedSymbol(symbolFromUrl);
    }
  }, [symbolFromUrl]);
  
  // Clear symbol filter
  const clearSymbolFilter = () => {
    setFocusedSymbol(null);
    searchParams.delete('symbol');
    setSearchParams(searchParams);
  };

  // Fetch available weeks for selected tier
  const { data: weeksData, isLoading: weeksLoading, error: weeksError } = useQuery({
    queryKey: ['spine', 'data', 'weeks', selectedTier],
    queryFn: () => client.queryWeeks(selectedTier, 20),
  });

  // Fetch symbols for selected week
  const { data: symbolsData, isLoading: symbolsLoading, error: symbolsError } = useQuery({
    queryKey: ['spine', 'data', 'symbols', selectedTier, selectedWeek, symbolLimit],
    queryFn: () => client.querySymbols(selectedTier, selectedWeek!, symbolLimit),
    enabled: !!selectedWeek,
  });
  
  // Fetch symbol history when a symbol is focused
  const { data: symbolHistory, isLoading: historyLoading, error: historyError } = useQuery({
    queryKey: ['spine', 'data', 'symbol-history', focusedSymbol, selectedTier],
    queryFn: () => client.getSymbolHistory(focusedSymbol!, selectedTier, 12),
    enabled: !!focusedSymbol,
  });

  const weeks = weeksData?.weeks ?? [];
  const symbols = symbolsData?.symbols ?? [];

  return (
    <div className="data-assets-page">
      <header className="page-header">
        <h1 className="page-title">Data Assets</h1>
        <p className="page-subtitle">Browse FINRA OTC transparency data by tier and week</p>
      </header>

      {/* Tier Selection */}
      <div className="tier-tabs">
        {TIERS.map((tier) => (
          <button
            key={tier.value}
            className={`tier-tab ${selectedTier === tier.value ? 'active' : ''}`}
            onClick={() => {
              setSelectedTier(tier.value);
              setSelectedWeek(null);
            }}
          >
            {tier.label}
          </button>
        ))}
      </div>

      {/* Symbol History Panel - shown when a symbol is focused */}
      {focusedSymbol && (
        <section className="card symbol-history-panel" style={{ marginBottom: '24px' }}>
          <header className="card-header">
            <h2>
              <code style={{ 
                background: 'var(--bg-tertiary)', 
                padding: '2px 8px', 
                borderRadius: '4px',
                marginRight: '8px',
              }}>
                {focusedSymbol}
              </code>
              History
            </h2>
            <button 
              className="btn-secondary" 
              onClick={clearSymbolFilter}
              style={{ fontSize: '12px', padding: '4px 12px' }}
            >
              ✕ Clear Filter
            </button>
          </header>
          <div className="card-body">
            {historyError ? (
              <div className="error-state">
                Failed to load history: {historyError instanceof Error ? historyError.message : 'Unknown error'}
              </div>
            ) : historyLoading ? (
              <SkeletonWidget type="list" />
            ) : symbolHistory && symbolHistory.history.length > 0 ? (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Week Ending</th>
                    <th className="text-right">Shares</th>
                    <th className="text-right">Trades</th>
                    <th className="text-right">Avg Price</th>
                  </tr>
                </thead>
                <tbody>
                  {symbolHistory.history.map((row: SymbolWeekData) => (
                    <tr key={row.week_ending}>
                      <td>{row.week_ending}</td>
                      <td className="text-right font-mono">{formatVolume(row.total_shares)}</td>
                      <td className="text-right font-mono">{row.total_trades.toLocaleString()}</td>
                      <td className="text-right font-mono">
                        {row.average_price !== null && row.average_price !== undefined
                          ? `$${row.average_price.toFixed(2)}`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state">
                <p>No history found for {focusedSymbol}</p>
              </div>
            )}
          </div>
        </section>
      )}

      <div className="data-grid">
        {/* Weeks Panel */}
        <section className="card weeks-panel">
          <header className="card-header">
            <h2>Available Weeks</h2>
            <span className="card-count">{weeks.length}</span>
          </header>
          <div className="card-body">
            {weeksError ? (
              <div className="error-state">
                Failed to load weeks: {weeksError instanceof Error ? weeksError.message : 'Unknown error'}
              </div>
            ) : weeksLoading ? (
              <SkeletonWidget type="list" />
            ) : weeks.length > 0 ? (
              <ul className="weeks-list">
                {weeks.map((week) => (
                  <WeekItem
                    key={week.week_ending}
                    week={week}
                    isSelected={selectedWeek === week.week_ending}
                    onClick={() => setSelectedWeek(week.week_ending)}
                  />
                ))}
              </ul>
            ) : (
              <NoDataEmptyState dataType="weeks" />
            )}
          </div>
        </section>

        {/* Symbols Panel */}
        <section className="card symbols-panel">
          <header className="card-header">
            <h2>
              Top Symbols
              {selectedWeek && <span className="week-label"> — Week of {selectedWeek}</span>}
            </h2>
            {selectedWeek && (
              <select
                className="limit-select"
                value={symbolLimit}
                onChange={(e) => setSymbolLimit(Number(e.target.value))}
              >
                <option value={10}>Top 10</option>
                <option value={25}>Top 25</option>
                <option value={50}>Top 50</option>
                <option value={100}>Top 100</option>
              </select>
            )}
          </header>
          <div className="card-body">
            {!selectedWeek ? (
              <div className="empty-state">
                <p>Select a week to view symbols</p>
              </div>
            ) : symbolsError ? (
              <div className="error-state">
                Failed to load symbols: {symbolsError instanceof Error ? symbolsError.message : 'Unknown error'}
              </div>
            ) : symbolsLoading ? (
              <SkeletonWidget type="list" />
            ) : symbols.length > 0 ? (
              <table className="data-table symbols-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Symbol</th>
                    <th className="text-right">Volume</th>
                    <th className="text-right">Avg Price</th>
                  </tr>
                </thead>
                <tbody>
                  {symbols.map((symbol, index) => (
                    <SymbolRow key={symbol.symbol} symbol={symbol} rank={index + 1} />
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state">
                <p>No symbols for this week</p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function WeekItem({ 
  week, 
  isSelected, 
  onClick 
}: { 
  week: WeekInfo; 
  isSelected: boolean; 
  onClick: () => void;
}) {
  return (
    <li 
      className={`week-item ${isSelected ? 'selected' : ''}`}
      onClick={onClick}
    >
      <span className="week-date">{week.week_ending}</span>
      <span className="week-count">{week.symbol_count.toLocaleString()} symbols</span>
    </li>
  );
}

function SymbolRow({ symbol, rank }: { symbol: SymbolInfo; rank: number }) {
  return (
    <tr>
      <td className="rank-cell">{rank}</td>
      <td>
        <code className="symbol-code">{symbol.symbol}</code>
      </td>
      <td className="text-right font-mono">
        {formatVolume(symbol.volume)}
      </td>
      <td className="text-right font-mono">
        {symbol.avg_price !== null && symbol.avg_price !== undefined
          ? `$${symbol.avg_price.toFixed(2)}`
          : '—'}
      </td>
    </tr>
  );
}

function formatVolume(volume: number): string {
  if (volume >= 1_000_000_000) return (volume / 1_000_000_000).toFixed(2) + 'B';
  if (volume >= 1_000_000) return (volume / 1_000_000).toFixed(2) + 'M';
  if (volume >= 1_000) return (volume / 1_000).toFixed(1) + 'K';
  return volume.toLocaleString();
}
