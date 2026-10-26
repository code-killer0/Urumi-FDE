import React, { useState, useEffect } from 'react';
import {
  Server, Plus, RefreshCw, Trash2, Power, ChevronDown,
  ChevronRight, Search, Activity, Layers, Container, AlertCircle, Wrench,
  Zap, Clock, Globe
} from 'lucide-react';
import { UpstreamServer, User } from '../types';
import { api } from '../api';

interface ServersTabProps {
  currentUser: User | null;
}

export const ServersTab: React.FC<ServersTabProps> = ({ currentUser }) => {
  const [servers, setServers] = useState<UpstreamServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [probing, setProbing] = useState<number | null>(null);
  const [scaleMode, setScaleMode] = useState(false);
  const [expandedServer, setExpandedServer] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [addMode, setAddMode] = useState<'url' | 'hosted'>('url');
  const [filterQuery, setFilterQuery] = useState('');

  const [formName, setFormName] = useState('');
  const [formSlug, setFormSlug] = useState('');
  const [formUrl, setFormUrl] = useState('');
  const [formToken, setFormToken] = useState('');
  const [formImage, setFormImage] = useState('');
  const [formEnv, setFormEnv] = useState('LOG_LEVEL=info\nPORT=8000');
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const fetchServers = async () => {
    try {
      setLoading(true);
      const data = await api.getServers();
      setServers(data);
    } catch (err: any) {
      console.error('Failed to fetch servers:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchServers(); }, []);

  const handleToggleServer = async (server: UpstreamServer) => {
    try {
      await api.updateServer(server.id, { enabled: !server.enabled });
      await fetchServers();
    } catch (err: any) {
      alert(`Error toggling server: ${err.message}`);
    }
  };

  const handleForceProbe = async (serverId: number) => {
    try {
      setProbing(serverId);
      await api.syncTools(serverId);
      await fetchServers();
    } catch (err: any) {
      alert(`Probe failed: ${err.message}`);
    } finally {
      setProbing(null);
    }
  };

  const handleDeleteServer = async (server: UpstreamServer) => {
    if (!confirm(`Remove '${server.name}' (${server.slug})?`)) return;
    try {
      await api.deleteServer(server.id);
      await fetchServers();
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const handleCreateServer = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      if (addMode === 'url') {
        await api.createServer({ name: formName, slug: formSlug, url: formUrl, credential: formToken || undefined, is_hosted: false });
      } else {
        const envLines = formEnv.split('\n');
        const env_vars: Record<string, string> = {};
        for (const line of envLines) {
          const [k, ...v] = line.split('=');
          if (k && k.trim()) env_vars[k.trim()] = v.join('=').trim();
        }
        await api.createServer({ name: formName, slug: formSlug, is_hosted: true, container_image: formImage, env_vars });
      }
      setShowAddModal(false);
      setFormName(''); setFormSlug(''); setFormUrl(''); setFormToken(''); setFormImage('');
      await fetchServers();
    } catch (err: any) {
      setFormError(err.message || 'Failed to create server');
    } finally {
      setSubmitting(false);
    }
  };

  const filteredServers = servers.filter((s) => {
    const q = filterQuery.toLowerCase();
    return s.name.toLowerCase().includes(q) || s.slug.toLowerCase().includes(q) ||
      s.cached_tools?.some((t) => t.name.toLowerCase().includes(q));
  });

  const totalTools = servers.reduce((acc, s) => acc + (s.cached_tools?.length || 0), 0);
  const totalCalls = servers.reduce((acc, s) => acc + s.total_calls, 0);
  const connectedCount = servers.filter(s => s.status === 'Connected').length;

  return (
    <div className="space-y-6 animate-fadeIn">

      {/* Header Banner */}
      <div className="card-raised overflow-hidden">
        {/* Accent gradient bar */}
        <div className="h-1 w-full bg-gradient-to-r from-indigo-500 via-violet-500 to-blue-500" />
        <div className="p-6">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center">
                  <Activity className="w-5 h-5 text-indigo-600" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-slate-800 tracking-tight">
                    Upstream MCP Server Registry
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Live tool mesh · collision namespacing · circuit breaker telemetry
                  </p>
                </div>
                <span className="text-[11px] px-2.5 py-0.5 rounded-full badge-emerald font-semibold hidden sm:inline-flex">
                  Streamable HTTP
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-3">
              {/* Scale Mode Toggle */}
              <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs">
                <Layers className={`w-4 h-4 ${scaleMode ? 'text-indigo-600' : 'text-slate-400'}`} />
                <div className="flex flex-col leading-none">
                  <span className="font-semibold text-slate-700 text-[11px]">Scale Mode</span>
                  <span className="text-[10px] text-slate-400">Meta-Tool Search</span>
                </div>
                <button
                  onClick={() => setScaleMode(!scaleMode)}
                  className={`ml-2 w-9 h-5 flex items-center rounded-full p-0.5 transition-colors ${scaleMode ? 'bg-indigo-600' : 'bg-slate-300'}`}
                >
                  <div className={`bg-white w-4 h-4 rounded-full shadow-sm transform transition-transform ${scaleMode ? 'translate-x-4' : 'translate-x-0'}`} />
                </button>
              </div>

              {currentUser?.role === 'admin' && (
                <button
                  onClick={() => setShowAddModal(true)}
                  className="btn-primary"
                >
                  <Plus className="w-4 h-4" />
                  <span>Add Server</span>
                </button>
              )}

              <button
                onClick={fetchServers}
                className="p-2 rounded-xl border border-slate-200 bg-white text-slate-500 hover:text-indigo-600 hover:border-indigo-200 transition-colors"
                title="Refresh"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-indigo-500' : ''}`} />
              </button>
            </div>
          </div>

          {/* Metric Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-5 border-t border-slate-100">
            {[
              { label: 'Registered', value: servers.length, sub: `${connectedCount} Active`, subColor: 'text-emerald-600', icon: Server },
              { label: 'Aggregated Tools', value: totalTools, sub: 'RBAC-gated', subColor: 'text-indigo-500', icon: Wrench },
              { label: 'Gateway Calls', value: totalCalls, sub: 'All clients', subColor: 'text-slate-400', icon: Zap },
              { label: 'Transport', value: 'HTTP/SSE', sub: 'JSON-RPC 2.0', subColor: 'text-slate-400', icon: Globe },
            ].map(({ label, value, sub, subColor, icon: Icon }) => (
              <div key={label} className="bg-slate-50 border border-slate-100 rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-medium text-slate-500">{label}</span>
                  <Icon className="w-3.5 h-3.5 text-slate-300" />
                </div>
                <div className="text-2xl font-bold text-slate-800">{value}</div>
                <span className={`text-[11px] ${subColor} mt-0.5 block`}>{sub}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Search Bar */}
      <div className="flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search servers, slugs or tool keywords..."
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            className="input-light pl-9"
          />
        </div>
        <span className="text-xs text-slate-400">
          {filteredServers.length} / {servers.length} servers
        </span>
      </div>

      {/* Server Cards */}
      <div className="space-y-3">
        {filteredServers.map((server) => {
          const isExpanded = expandedServer === server.slug;
          const isHealthy = server.status === 'Connected';
          const isProbeLoading = probing === server.id;
          const isUnreachable = server.status === 'Unreachable';
          const isHostedOffline = server.is_hosted && isUnreachable;

          return (
            <div
              key={server.id}
              className={`card transition-all duration-200 overflow-hidden ${
                !server.enabled ? 'opacity-60' : 'hover:shadow-md hover:border-slate-300'
              }`}
            >
              {/* Status accent line */}
              <div className={`h-0.5 w-full ${
                isHealthy ? 'bg-emerald-400' : isUnreachable ? 'bg-rose-400' : 'bg-slate-200'
              }`} />

              <div className="p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                {/* Server Info */}
                <div className="flex items-start gap-3.5">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                    server.is_hosted
                      ? 'bg-purple-50 border border-purple-200 text-purple-600'
                      : 'bg-indigo-50 border border-indigo-100 text-indigo-600'
                  }`}>
                    {server.is_hosted ? <Container className="w-5 h-5" /> : <Server className="w-5 h-5" />}
                  </div>

                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-slate-800 text-sm">{server.name}</h3>
                      <span className="font-mono text-xs px-2 py-0.5 rounded-lg bg-slate-100 text-slate-600 border border-slate-200">
                        {server.slug}
                      </span>
                      {server.is_hosted && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full badge-purple font-semibold flex items-center gap-1">
                          <Container className="w-3 h-3" /> Hosted Container
                        </span>
                      )}
                    </div>

                    <p className="text-[11px] font-mono text-slate-400 mt-1 truncate max-w-md">
                      {server.url}
                    </p>

                    {/* Error message */}
                    {server.last_error && (
                      <div className="flex items-start gap-1.5 text-xs text-rose-600 mt-2 bg-rose-50 border border-rose-200 rounded-lg px-2.5 py-1.5">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                        <div>
                          <span className="truncate block">{server.last_error}</span>
                          {isHostedOffline && (
                            <span className="text-[10px] text-rose-500 mt-0.5 block">
                              ⚠ Hosted container is running in Kubernetes only. In local dev mode, this URL is unreachable — this is expected.
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Status & Actions */}
                <div className="flex flex-wrap items-center gap-4 lg:justify-end">
                  {/* Status */}
                  <div className="flex items-center gap-1.5">
                    <span className={`w-2 h-2 rounded-full ${
                      isHealthy ? 'bg-emerald-500 shadow-sm shadow-emerald-200' :
                      isUnreachable ? 'bg-rose-500 shadow-sm shadow-rose-200' :
                      'bg-amber-400 animate-pulse'
                    }`} />
                    <span className={`text-xs font-semibold ${
                      isHealthy ? 'text-emerald-600' : isUnreachable ? 'text-rose-600' : 'text-amber-600'
                    }`}>
                      {server.status}
                    </span>
                  </div>

                  {/* Latency */}
                  <div className="text-right">
                    <div className="flex items-center gap-1 text-xs font-mono font-semibold text-slate-700">
                      <Clock className="w-3 h-3 text-slate-400" />
                      {server.latency_ms > 0 ? `${server.latency_ms.toFixed(1)} ms` : '—'}
                    </div>
                    <span className="text-[10px] text-slate-400 block">Latency</span>
                  </div>

                  {/* Tools count */}
                  <div className="text-right">
                    <span className="text-xs font-mono font-semibold text-slate-700">{server.cached_tools?.length || 0}</span>
                    <span className="text-[10px] text-slate-400 block">Tools</span>
                  </div>

                  {/* Controls */}
                  <div className="flex items-center gap-1 border-l border-slate-200 pl-3">
                    <button
                      onClick={() => handleForceProbe(server.id)}
                      disabled={isProbeLoading}
                      className="p-1.5 text-slate-400 hover:text-indigo-600 rounded-lg hover:bg-indigo-50 transition-colors"
                      title="Force Probe & Sync Tools"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isProbeLoading ? 'animate-spin text-indigo-500' : ''}`} />
                    </button>

                    {currentUser?.role === 'admin' && (
                      <>
                        <button
                          onClick={() => handleToggleServer(server)}
                          className={`p-1.5 rounded-lg transition-colors ${
                            server.enabled ? 'text-emerald-600 hover:bg-emerald-50' : 'text-slate-400 hover:bg-slate-100'
                          }`}
                          title={server.enabled ? 'Disable' : 'Enable'}
                        >
                          <Power className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleDeleteServer(server)}
                          className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                          title="Remove"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </>
                    )}

                    <button
                      onClick={() => setExpandedServer(isExpanded ? null : server.slug)}
                      className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors ml-1"
                    >
                      {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Expanded Tools Panel */}
              {isExpanded && (
                <div className="border-t border-slate-100 bg-slate-50/80 p-5 rounded-b-2xl">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Wrench className="w-3.5 h-3.5 text-indigo-500" />
                      <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                        Exposed Tools ({server.cached_tools?.length || 0})
                      </h4>
                    </div>
                    <span className="text-[11px] text-slate-400">
                      Namespace: <code className="text-indigo-600 font-mono font-semibold">{server.slug}__tool_name</code>
                    </span>
                  </div>

                  {server.cached_tools && server.cached_tools.length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {server.cached_tools.map((tool) => (
                        <div key={tool.name} className="bg-white border border-slate-200 rounded-xl p-3 text-xs hover:border-indigo-200 hover:shadow-sm transition-all">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-mono font-semibold text-indigo-600">
                              {server.slug}__{tool.name}
                            </span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-slate-100 text-slate-500 border border-slate-200">
                              {tool.inputSchema?.type || 'object'}
                            </span>
                          </div>
                          <p className="text-slate-500 line-clamp-2 text-[11px] leading-relaxed">
                            {tool.description || 'No description provided.'}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-xs text-slate-400">
                      <Server className="w-6 h-6 text-slate-300 mx-auto mb-2" />
                      No tools synchronized. Click the refresh icon to probe.
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {filteredServers.length === 0 && !loading && (
          <div className="card p-12 text-center">
            <Server className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <p className="text-sm font-medium text-slate-500">No servers found</p>
            <p className="text-xs text-slate-400 mt-1">Add an upstream MCP server or clear your search filter.</p>
          </div>
        )}
      </div>

      {/* Add Server Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-lg w-full p-6 shadow-2xl shadow-slate-200/50 relative">
            <div className="flex items-center gap-3 mb-1">
              <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center">
                <Plus className="w-4 h-4 text-indigo-600" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-800">Register Upstream MCP Server</h3>
                <p className="text-xs text-slate-500">Connect an existing service or deploy a container into Kubernetes.</p>
              </div>
            </div>

            {/* Mode Tabs */}
            <div className="flex border-b border-slate-100 mt-4 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setAddMode('url')}
                className={`py-2 px-4 border-b-2 transition-colors ${addMode === 'url' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
              >
                🔗 Connect by URL
              </button>
              <button
                type="button"
                onClick={() => setAddMode('hosted')}
                className={`py-2 px-4 border-b-2 transition-colors ${addMode === 'hosted' ? 'border-purple-500 text-purple-600' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
              >
                📦 Deploy Container Image
              </button>
            </div>

            {formError && (
              <div className="bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-xl p-3 mt-4">
                {formError}
              </div>
            )}

            <form onSubmit={handleCreateServer} className="space-y-4 mt-4 text-xs">
              <div>
                <label className="block text-slate-600 font-semibold mb-1.5">Server Name</label>
                <input type="text" required placeholder="e.g. Warehouse Inventory Scanner"
                  value={formName} onChange={(e) => setFormName(e.target.value)} className="input-light" />
              </div>
              <div>
                <label className="block text-slate-600 font-semibold mb-1.5">Slug (Namespacing prefix)</label>
                <input type="text" required pattern="^[a-z0-9_]+$" placeholder="e.g. warehouse"
                  value={formSlug} onChange={(e) => setFormSlug(e.target.value)} className="input-light font-mono" />
                <span className="text-[10px] text-slate-400 mt-1 block">
                  Tools will be namespaced as: <span className="text-indigo-600 font-mono font-semibold">{formSlug || 'slug'}__tool_name</span>
                </span>
              </div>

              {addMode === 'url' ? (
                <>
                  <div>
                    <label className="block text-slate-600 font-semibold mb-1.5">Upstream URL</label>
                    <input type="url" required placeholder="http://service.urumi-system.svc.cluster.local:8000"
                      value={formUrl} onChange={(e) => setFormUrl(e.target.value)} className="input-light font-mono" />
                  </div>
                  <div>
                    <label className="block text-slate-600 font-semibold mb-1.5">Bearer Token <span className="text-slate-400 font-normal">(encrypted at rest via Fernet)</span></label>
                    <input type="password" placeholder="Optional bearer token"
                      value={formToken} onChange={(e) => setFormToken(e.target.value)} className="input-light font-mono" />
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="block text-slate-600 font-semibold mb-1.5">Container Image</label>
                    <input type="text" required placeholder="urumi/warehouse-scanner:v1.0"
                      value={formImage} onChange={(e) => setFormImage(e.target.value)} className="input-light font-mono" />
                  </div>
                  <div>
                    <label className="block text-slate-600 font-semibold mb-1.5">Environment Variables <span className="text-slate-400 font-normal">(KEY=VALUE per line)</span></label>
                    <textarea rows={3} value={formEnv} onChange={(e) => setFormEnv(e.target.value)}
                      className="input-light font-mono resize-none" />
                  </div>
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-[11px] text-amber-700">
                    <strong>Note:</strong> Hosted containers are deployed to Kubernetes and are only reachable inside the cluster. In local dev mode (without a K8s cluster), the server will show as Unreachable — this is expected behavior.
                  </div>
                </>
              )}

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button type="button" onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-xl transition-colors">
                  Cancel
                </button>
                <button type="submit" disabled={submitting}
                  className={`btn-primary ${submitting ? 'opacity-60 cursor-not-allowed' : ''}`}>
                  {submitting ? 'Registering...' : 'Register Server'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
