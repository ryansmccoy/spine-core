import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Play,
  GitBranch,
  Clock,
  Skull,
  ShieldCheck,
  BarChart3,
  Database,
  BookOpen,
  Gamepad2,
  ChevronLeft,
  ChevronRight,
  Zap,
  type LucideIcon,
} from 'lucide-react';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  section?: string;
}

const NAV: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, section: 'overview' },
  { to: '/runs', label: 'Runs', icon: Play, section: 'execution' },
  { to: '/workflows', label: 'Workflows', icon: GitBranch, section: 'execution' },
  { to: '/schedules', label: 'Schedules', icon: Clock, section: 'execution' },
  { to: '/dlq', label: 'Dead Letters', icon: Skull, section: 'operations' },
  { to: '/quality', label: 'Quality', icon: ShieldCheck, section: 'operations' },
  { to: '/stats', label: 'Stats & Workers', icon: BarChart3, section: 'operations' },
  { to: '/database', label: 'Database', icon: Database, section: 'operations' },
  { to: '/functions', label: 'Functions', icon: Zap, section: 'develop' },
  { to: '/examples', label: 'Examples', icon: BookOpen, section: 'develop' },
  { to: '/playground', label: 'Playground', icon: Gamepad2, section: 'develop' },
];

const SECTION_LABELS: Record<string, string> = {
  overview: 'OVERVIEW',
  execution: 'EXECUTION',
  operations: 'OPERATIONS',
  develop: 'DEVELOP',
};

/** Build breadcrumb from current path */
function useBreadcrumb() {
  const { pathname } = useLocation();
  const parts = pathname.split('/').filter(Boolean);
  const crumbs: { label: string; path?: string }[] = [];

  if (parts.length >= 1) {
    const nav = NAV.find((n) => n.to === `/${parts[0]}`);
    crumbs.push({ label: nav?.label ?? parts[0], path: `/${parts[0]}` });
  }
  if (parts.length >= 2) {
    crumbs.push({ label: parts[1].length > 12 ? parts[1].slice(0, 12) + '…' : parts[1] });
  }
  return crumbs;
}

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false);
  const breadcrumbs = useBreadcrumb();

  // Group nav items by section
  let lastSection = '';

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <nav
        className={`${collapsed ? 'w-16' : 'w-60'} shrink-0 bg-spine-950 text-white flex flex-col transition-all duration-200 border-r border-spine-900`}
      >
        {/* Brand */}
        <div className={`flex items-center gap-3 ${collapsed ? 'px-3 justify-center' : 'px-5'} py-5 border-b border-white/[0.06]`}>
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-spine-400 to-spine-600 flex items-center justify-center shrink-0">
            <Zap size={18} className="text-white" />
          </div>
          {!collapsed && (
            <div>
              <h1 className="text-sm font-semibold tracking-tight text-white">spine-core</h1>
              <p className="text-[10px] text-spine-400 leading-tight">execution engine</p>
            </div>
          )}
        </div>

        {/* Navigation */}
        <ul className="flex-1 py-2 overflow-y-auto">
          {NAV.map((n) => {
            const showSection = n.section !== lastSection;
            if (showSection) lastSection = n.section ?? '';

            return (
              <li key={n.to}>
                {showSection && !collapsed && n.section && (
                  <div className="px-5 pt-4 pb-1.5">
                    <span className="text-[10px] font-semibold tracking-widest text-spine-500/70 uppercase">
                      {SECTION_LABELS[n.section]}
                    </span>
                  </div>
                )}
                {showSection && collapsed && n.section && (
                  <div className="mx-3 my-2 border-t border-white/[0.06]" />
                )}
                <NavLink
                  to={n.to}
                  title={collapsed ? n.label : undefined}
                  className={({ isActive }) =>
                    `group flex items-center gap-3 mx-2 rounded-md text-[13px] transition-all duration-150 ${
                      collapsed ? 'justify-center px-0 py-2.5' : 'px-3 py-2'
                    } ${
                      isActive
                        ? 'bg-spine-600/20 text-white font-medium shadow-sm shadow-spine-500/10'
                        : 'text-spine-300 hover:bg-white/[0.06] hover:text-white'
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span className="absolute left-0 w-[3px] h-5 rounded-r-full bg-spine-400" />
                      )}
                      <n.icon size={18} className={`shrink-0 ${isActive ? 'text-spine-300' : 'text-spine-500 group-hover:text-spine-300'}`} />
                      {!collapsed && <span>{n.label}</span>}
                    </>
                  )}
                </NavLink>
              </li>
            );
          })}
        </ul>

        {/* Footer: collapse toggle + version */}
        <div className="border-t border-white/[0.06]">
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="flex items-center justify-center w-full py-3 text-spine-500 hover:text-spine-300 transition-colors"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
          {!collapsed && (
            <div className="px-5 pb-3 text-[10px] text-spine-600 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
              v0.3.0 &middot; API connected
            </div>
          )}
        </div>
      </nav>

      {/* Main content area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar with breadcrumbs */}
        <header className="h-12 shrink-0 bg-white border-b border-gray-200 flex items-center px-6 gap-3">
          <nav className="flex items-center gap-1.5 text-sm">
            <span className="text-gray-400">spine</span>
            {breadcrumbs.map((c, i) => (
              <span key={i} className="flex items-center gap-1.5">
                <span className="text-gray-300">/</span>
                {c.path && i < breadcrumbs.length - 1 ? (
                  <NavLink to={c.path} className="text-gray-500 hover:text-gray-700 transition-colors">
                    {c.label}
                  </NavLink>
                ) : (
                  <span className="text-gray-900 font-medium">{c.label}</span>
                )}
              </span>
            ))}
          </nav>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
