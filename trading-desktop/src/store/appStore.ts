/**
 * Global application state using Zustand
 */

import { create } from 'zustand';

interface AppState {
  // Current active symbol (context linking)
  activeSymbol: string | null;
  setActiveSymbol: (symbol: string) => void;
  
  // Watchlist
  watchlist: string[];
  addToWatchlist: (symbol: string) => void;
  removeFromWatchlist: (symbol: string) => void;
  
  // UI State
  sidebarOpen: boolean;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Active symbol - all widgets react to this
  activeSymbol: 'AAPL',
  setActiveSymbol: (symbol) => set({ activeSymbol: symbol.toUpperCase() }),
  
  // Watchlist
  watchlist: ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA'],
  addToWatchlist: (symbol) =>
    set((state) => ({
      watchlist: state.watchlist.includes(symbol.toUpperCase())
        ? state.watchlist
        : [...state.watchlist, symbol.toUpperCase()],
    })),
  removeFromWatchlist: (symbol) =>
    set((state) => ({
      watchlist: state.watchlist.filter((s) => s !== symbol.toUpperCase()),
    })),
  
  // UI
  sidebarOpen: true,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
}));
