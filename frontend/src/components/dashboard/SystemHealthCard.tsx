/**
 * System health card showing API, database, and worker status.
 */

import { Server, Database, HardDrive } from 'lucide-react';

interface SystemHealthProps {
  apiStatus?: string;
  dbConnected?: boolean;
  dbBackend?: string;
  dbLatencyMs?: number;
  workerCount?: number;
}

function HealthRow({
  icon: Icon,
  label,
  status,
  detail,
  ok,
}: {
  icon: typeof Server;
  label: string;
  status: string;
  detail?: string;
  ok: boolean;
}) {
  return (
    <div className="flex items-center gap-3 py-1.5">
      <Icon size={16} className="text-gray-400 shrink-0" />
      <span className="text-sm text-gray-700 w-16">{label}</span>
      <span className={`w-2 h-2 rounded-full shrink-0 ${ok ? 'bg-green-500' : 'bg-red-500'}`} />
      <span className="text-sm font-medium">{status}</span>
      {detail && <span className="text-xs text-gray-400 ml-1">{detail}</span>}
    </div>
  );
}

export default function SystemHealthCard({
  apiStatus,
  dbConnected,
  dbBackend,
  dbLatencyMs,
  workerCount,
}: SystemHealthProps) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <h3 className="text-sm font-medium text-gray-700 mb-2">System Health</h3>
      <div className="space-y-0.5">
        <HealthRow
          icon={Server}
          label="API"
          status={apiStatus === 'healthy' ? 'Healthy' : apiStatus ?? 'Unknown'}
          ok={apiStatus === 'healthy'}
        />
        <HealthRow
          icon={Database}
          label="DB"
          status={dbConnected ? 'Connected' : 'Down'}
          detail={dbConnected ? `${dbBackend ?? ''} ${dbLatencyMs != null ? `${dbLatencyMs.toFixed(0)}ms` : ''}`.trim() : undefined}
          ok={dbConnected ?? false}
        />
        {workerCount !== undefined && (
          <HealthRow
            icon={HardDrive}
            label="Workers"
            status={`${workerCount} active`}
            ok={workerCount > 0}
          />
        )}
      </div>
    </div>
  );
}
