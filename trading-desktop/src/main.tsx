import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SpineProvider } from './api';
import TradingDesktop from './TradingDesktop';
import DashboardLayout from './dashboard/DashboardLayout';
import OverviewPage from './dashboard/pages/OverviewPage';
import PipelinesPage from './dashboard/pages/PipelinesPage';
import JobsPage from './dashboard/pages/JobsPage';
import QueuesPage from './dashboard/pages/QueuesPage';
import DataAssetsPage from './dashboard/pages/DataAssetsPage';
import IncidentsPage from './dashboard/pages/IncidentsPage';
import SettingsPage from './dashboard/pages/SettingsPage';
import { RecentRunsPage, RunDetailPage } from './dashboard/pages/orchestrator';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <SpineProvider>
        <BrowserRouter>
          <Routes>
            {/* Trading Desktop */}
            <Route path="/trading" element={<TradingDesktop />} />
            
            {/* Control Plane Dashboard */}
            <Route path="/dashboard" element={<DashboardLayout />}>
              <Route index element={<OverviewPage />} />
              <Route path="pipelines" element={<PipelinesPage />} />
              <Route path="jobs" element={<JobsPage />} />
              <Route path="queues" element={<QueuesPage />} />
              <Route path="data" element={<DataAssetsPage />} />
              <Route path="orchestrator" element={<RecentRunsPage />} />
              <Route path="orchestrator/:executionId" element={<RunDetailPage />} />
              <Route path="incidents" element={<IncidentsPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>
            
            {/* Default redirect to dashboard */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </SpineProvider>
    </QueryClientProvider>
  </StrictMode>
);
