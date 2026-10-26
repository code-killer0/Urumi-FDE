import React, { useState } from 'react';
import {
  Server, MessageSquare, Store, Key, ShieldCheck,
  Copy, Check, UserCheck, Activity, Terminal
} from 'lucide-react';
import { User } from '../types';

export type TabType = 'servers' | 'chat' | 'stores' | 'keys' | 'audit';

export interface NavbarProps {
  currentUser: User | null;
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
  onSwitchUser: (role: 'admin' | 'member') => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentUser,
  activeTab,
  setActiveTab,
  onSwitchUser,
}) => {
  const [copied, setCopied] = useState(false);
  const mcpEndpoint = `${window.location.protocol}//${window.location.host}/mcp`;

  const copyEndpoint = () => {
    navigator.clipboard.writeText(mcpEndpoint);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const navItems: { id: TabType; label: string; icon: any; badge: string | null }[] = [
    { id: 'servers', label: 'MCP Servers',       icon: Server,       badge: null },
    { id: 'chat',    label: 'Chat Agent',         icon: MessageSquare, badge: 'DoD' },
    { id: 'stores',  label: 'Multi-Store Cloud',  icon: Store,         badge: 'Bonus' },
    { id: 'keys',    label: 'Team & Keys',         icon: Key,           badge: null },
    { id: 'audit',   label: 'Audit Trail',         icon: ShieldCheck,   badge: 'SHA-256' },
  ];

  return (
    <header className="border-b border-slate-200 bg-white/90 backdrop-blur-md sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Top Row: Brand + MCP Endpoint + User Switcher */}
        <div className="flex items-center justify-between h-16 gap-4">

          {/* Logo & Brand */}
          <div className="flex items-center space-x-3 shrink-0">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 flex items-center justify-center shadow-md shadow-indigo-200">
              <Activity className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-lg tracking-tight gradient-text">
                  Urumi Platform
                </span>
                <span className="text-[11px] px-2 py-0.5 rounded-full badge-indigo font-semibold">
                  v1.0 HA
                </span>
              </div>
              <p className="text-[11px] text-slate-400 hidden sm:block leading-none mt-0.5">
                Kubernetes WooCommerce Engine & Team MCP Gateway
              </p>
            </div>
          </div>

          {/* MCP Endpoint Copier */}
          <div className="hidden lg:flex items-center space-x-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-600 font-mono flex-1 max-w-sm">
            <Terminal className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
            <span className="text-slate-400 shrink-0">MCP:</span>
            <span className="text-indigo-600 truncate">{mcpEndpoint}</span>
            <button
              onClick={copyEndpoint}
              className="ml-1 p-1 hover:bg-slate-200 rounded-lg transition-colors shrink-0"
              title="Copy Streamable HTTP MCP URL"
            >
              {copied
                ? <Check className="w-3.5 h-3.5 text-emerald-500" />
                : <Copy className="w-3.5 h-3.5 text-slate-400" />}
            </button>
          </div>

          {/* User Switcher */}
          <div className="flex items-center space-x-3 shrink-0">
            <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200 text-xs gap-1">
              <button
                onClick={() => onSwitchUser('admin')}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg font-semibold transition-all duration-150 ${
                  currentUser?.role === 'admin'
                    ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-200'
                    : 'text-slate-500 hover:text-slate-700 hover:bg-white'
                }`}
              >
                <UserCheck className="w-3.5 h-3.5" />
                <span>Admin</span>
              </button>
              <button
                onClick={() => onSwitchUser('member')}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg font-semibold transition-all duration-150 ${
                  currentUser?.role === 'member'
                    ? 'bg-emerald-600 text-white shadow-sm shadow-emerald-200'
                    : 'text-slate-500 hover:text-slate-700 hover:bg-white'
                }`}
              >
                <UserCheck className="w-3.5 h-3.5" />
                <span>Member</span>
              </button>
            </div>

            <div className="hidden md:flex flex-col text-right">
              <span className="text-xs font-semibold text-slate-700">
                {currentUser?.email || 'Loading...'}
              </span>
              <span className={`text-[10px] font-bold uppercase tracking-wider ${
                currentUser?.role === 'admin' ? 'text-indigo-600' : 'text-emerald-600'
              }`}>
                {currentUser?.role || 'Guest'}
              </span>
            </div>
          </div>
        </div>

        {/* Tab Navigation Row */}
        <div className="flex space-x-1 overflow-x-auto pb-2 scrollbar-none">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center space-x-2 px-3.5 py-2 rounded-xl text-xs font-medium whitespace-nowrap transition-all duration-150 ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200'
                    : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-white' : 'text-slate-400'}`} />
                <span>{item.label}</span>
                {item.badge && (
                  <span className={`text-[9px] px-1.5 py-0.5 rounded-md font-bold ${
                    isActive
                      ? 'bg-white/20 text-white'
                      : item.badge === 'Bonus'
                        ? 'bg-amber-100 text-amber-700 border border-amber-200'
                        : 'bg-indigo-50 text-indigo-600 border border-indigo-200'
                  }`}>
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
};
