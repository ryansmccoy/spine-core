import { create } from 'zustand';

interface TemporalContextState {
  mode: 'live' | 'as_of' | 'capture';
  asOf: string | null;
  captureId: string | null;
  lastRefresh: Date;
  setMode: (mode: 'live' | 'as_of' | 'capture') => void;
  setAsOf: (asOf: string | null) => void;
  setCaptureId: (captureId: string | null) => void;
  refresh: () => void;
}

export const useTemporalContext = create<TemporalContextState>((set) => ({
  mode: 'live',
  asOf: null,
  captureId: null,
  lastRefresh: new Date(),
  setMode: (mode) => set({ mode }),
  setAsOf: (asOf) => set({ asOf }),
  setCaptureId: (captureId) => set({ captureId }),
  refresh: () => set({ lastRefresh: new Date() }),
}));
