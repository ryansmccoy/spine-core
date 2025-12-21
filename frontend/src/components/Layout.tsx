import { NavLink, Outlet } from 'react-router-dom';

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: '□' },
  { to: '/runs', label: 'Runs', icon: '▶' },
  { to: '/workflows', label: 'Workflows', icon: '⥤' },
  { to: '/schedules', label: 'Schedules', icon: '⏱' },
  { to: '/dlq', label: 'Dead Letters', icon: '✗' },
  { to: '/quality', label: 'Quality', icon: '✓' },
  { to: '/stats', label: 'Stats & Workers', icon: '⚡' },
];

export default function Layout() {
  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <nav className="w-56 shrink-0 bg-spine-900 text-white flex flex-col">
        <div className="px-4 py-5 border-b border-spine-800">
          <h1 className="text-lg font-bold tracking-tight">spine-core</h1>
          <p className="text-xs text-spine-400">execution dashboard</p>
        </div>
        <ul className="flex-1 py-3 space-y-0.5 overflow-y-auto">
          {NAV.map((n) => (
            <li key={n.to}>
              <NavLink
                to={n.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                    isActive
                      ? 'bg-spine-700 text-white font-medium'
                      : 'text-spine-300 hover:bg-spine-800 hover:text-white'
                  }`
                }
              >
                <span className="text-base">{n.icon}</span>
                {n.label}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="px-4 py-3 text-[10px] text-spine-500 border-t border-spine-800">
          v0.3.0 &middot; port 12000
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}
