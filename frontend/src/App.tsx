import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Runs from './pages/Runs';
import RunDetail from './pages/RunDetail';
import Workflows from './pages/Workflows';
import WorkflowDetailPage from './pages/WorkflowDetail';
import Schedules from './pages/Schedules';
import DLQ from './pages/DLQ';
import Quality from './pages/Quality';
import Stats from './pages/Stats';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/runs/:runId" element={<RunDetail />} />
          <Route path="/workflows" element={<Workflows />} />
          <Route path="/workflows/:name" element={<WorkflowDetailPage />} />
          <Route path="/schedules" element={<Schedules />} />
          <Route path="/dlq" element={<DLQ />} />
          <Route path="/quality" element={<Quality />} />
          <Route path="/stats" element={<Stats />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
