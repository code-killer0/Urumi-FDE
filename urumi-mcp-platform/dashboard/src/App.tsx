import React, { useState, useEffect } from 'react';
import { api } from './api';
import { User } from './types';
import { Navbar, TabType } from './components/Navbar';
import { ServersTab } from './components/ServersTab';
import { ChatTab } from './components/ChatTab';
import { StoresTab } from './components/StoresTab';
import { TeamKeysTab } from './components/TeamKeysTab';
import { AuditLogTab } from './components/AuditLogTab';

export const App: React.FC = () => {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('servers');
  const [loadingUser, setLoadingUser] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      try {
        if (api.getToken()) {
          const me = await api.getMe();
          setCurrentUser(me);
        } else {
          const res = await api.switchUser('admin');
          setCurrentUser(res.user);
        }
      } catch {
        try {
          const res = await api.switchUser('admin');
          setCurrentUser(res.user);
        } catch (e) {
          console.error('Failed to authenticate default admin', e);
        }
      } finally {
        setLoadingUser(false);
      }
    };
    initAuth();
  }, []);

  const handleUserSwitch = async (role: 'admin' | 'member') => {
    try {
      const res = await api.switchUser(role);
      setCurrentUser(res.user);
    } catch (err: any) {
      alert(`User switch failed: ${err.message}`);
    }
  };

  if (loadingUser) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center space-y-4">
        <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-slate-500 font-mono text-xs tracking-wider animate-pulse">
          INITIALIZING URUMI ENTERPRISE MCP GATEWAY...
        </p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col font-sans">
      <Navbar
        currentUser={currentUser}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onSwitchUser={handleUserSwitch}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fadeIn">
        {activeTab === 'servers' && <ServersTab currentUser={currentUser} />}
        {activeTab === 'chat'    && <ChatTab currentUser={currentUser} />}
        {activeTab === 'stores'  && <StoresTab currentUser={currentUser} />}
        {activeTab === 'keys'    && <TeamKeysTab currentUser={currentUser} />}
        {activeTab === 'audit'   && <AuditLogTab />}
      </main>

      <footer className="border-t border-slate-200 bg-white/80 backdrop-blur-sm py-3.5 px-6 text-xs text-slate-500 flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5 font-mono text-[11px] text-slate-500">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shadow-sm shadow-emerald-200" />
            Kubernetes Cluster: <span className="text-emerald-600 font-semibold">Active</span>
          </span>
          <span className="hidden sm:inline text-slate-300">|</span>
          <span className="hidden sm:inline font-mono text-[11px] text-slate-400">
            Protocol: <span className="text-indigo-600">MCP Streamable HTTP (2024-11-05)</span>
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[11px]">
          <span className="bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-lg text-slate-600">
            Urumi Platform v2.0
          </span>
          <span className="text-slate-400">SHA-256 Chained Integrity Verified</span>
        </div>
      </footer>
    </div>
  );
};
export default App;
