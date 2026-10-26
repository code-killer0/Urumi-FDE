import React, { useState, useEffect } from 'react';
import {
  Store, Plus, ExternalLink, Trash2, RefreshCw,
  Shield, Database, Cpu, CheckCircle2, Clock, AlertTriangle, Layers
} from 'lucide-react';
import { ProvisionedStore, User } from '../types';
import { api } from '../api';

interface StoresTabProps {
  currentUser: User | null;
}

export const StoresTab: React.FC<StoresTabProps> = ({ currentUser }) => {
  const [stores, setStores] = useState<ProvisionedStore[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStores = async () => {
    try {
      setLoading(true);
      const data = await api.getStores();
      setStores(data);
    } catch (err: any) {
      console.error('Failed to load stores:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStores();
    const interval = setInterval(fetchStores, 10000); // 10s auto refresh
    return () => clearInterval(interval);
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      await api.createStore({ name, slug });
      setShowCreateModal(false);
      setName('');
      setSlug('');
      await fetchStores();
    } catch (err: any) {
      setError(err.message || 'Failed to provision store');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (store: ProvisionedStore) => {
    if (!confirm(`Are you sure you want to delete store '${store.name}' (${store.slug})? This will purge its Kubernetes namespace and all PVCs.`)) return;
    try {
      await api.deleteStore(store.id);
      await fetchStores();
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const maxStores = 3;
  const userStoreCount = stores.length;

  return (
    <div className="space-y-6">
      {/* Banner Deck */}
      <div className="bg-gradient-to-r from-slate-900 via-amber-950/20 to-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-xl font-bold text-white tracking-tight">
                Multi-Store Kubernetes Cloud Engine
              </h2>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-medium">
                Bonus Feature
              </span>
            </div>
            <p className="text-sm text-slate-400 mt-1 max-w-2xl">
              Automated provisioning of isolated WooCommerce tenants in dedicated namespaces (<code className="text-amber-300 font-mono">urumi-store-{'{slug}'}</code>) with ResourceQuotas, zero-trust NetworkPolicies, and dedicated Streamable HTTP MCP servers.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <div className="bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs flex items-center space-x-3">
              <span className="text-slate-400 font-medium">Tenant Quota:</span>
              <div className="flex items-center space-x-1.5">
                <span className="font-bold text-white font-mono">{userStoreCount} / {maxStores}</span>
                <span className="text-[10px] text-slate-500">Stores</span>
              </div>
            </div>

            <button
              onClick={() => setShowCreateModal(true)}
              disabled={userStoreCount >= maxStores && currentUser?.role !== 'admin'}
              className="flex items-center space-x-2 bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400 disabled:opacity-50 text-white px-4 py-2 rounded-xl text-xs font-semibold shadow-lg shadow-amber-600/20 transition-all"
            >
              <Plus className="w-4 h-4" />
              <span>Create Store</span>
            </button>

            <button
              onClick={fetchStores}
              className="p-2 rounded-xl border border-slate-800 bg-slate-950 text-slate-400 hover:text-white transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Feature Highlights Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 mt-6 pt-6 border-t border-slate-800/80 text-xs">
          <div className="flex items-center space-x-3 bg-slate-950/60 border border-slate-800/80 rounded-xl p-3">
            <Shield className="w-5 h-5 text-emerald-400 shrink-0" />
            <div>
              <span className="font-semibold text-slate-200 block">Namespace Isolation</span>
              <span className="text-slate-400 text-[11px]">Default-deny NetworkPolicy restricts cross-tenant talk</span>
            </div>
          </div>

          <div className="flex items-center space-x-3 bg-slate-950/60 border border-slate-800/80 rounded-xl p-3">
            <Database className="w-5 h-5 text-indigo-400 shrink-0" />
            <div>
              <span className="font-semibold text-slate-200 block">Dedicated Storage & DB</span>
              <span className="text-slate-400 text-[11px]">Independent MariaDB + PVC volumes per tenant</span>
            </div>
          </div>

          <div className="flex items-center space-x-3 bg-slate-950/60 border border-slate-800/80 rounded-xl p-3">
            <Cpu className="w-5 h-5 text-cyan-400 shrink-0" />
            <div>
              <span className="font-semibold text-slate-200 block">Auto-Registered MCP</span>
              <span className="text-slate-400 text-[11px]">Tools instantly appear as <code className="text-cyan-300">store_{'{slug}'}__*</code></span>
            </div>
          </div>
        </div>
      </div>

      {/* Stores Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {stores.map((store) => {
          const isReady = store.status === 'Ready';
          const isFailed = store.status === 'Failed';
          const isProvisioning = store.status === 'Provisioning';

          return (
            <div
              key={store.id}
              className="bg-slate-900 border border-slate-800 hover:border-slate-700/80 rounded-2xl p-5 shadow-lg transition-all"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-xl bg-amber-950/60 border border-amber-500/30 flex items-center justify-center text-amber-400">
                    <Store className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-bold text-slate-100 text-sm">{store.name}</h3>
                    <span className="font-mono text-xs text-amber-400 font-medium">
                      {store.slug}
                    </span>
                  </div>
                </div>

                {/* Status Badge */}
                <div className="flex items-center space-x-1.5">
                  {isReady && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
                  {isProvisioning && <Clock className="w-4 h-4 text-amber-400 animate-spin" />}
                  {isFailed && <AlertTriangle className="w-4 h-4 text-rose-400" />}
                  <span className={`text-xs font-semibold ${
                    isReady ? 'text-emerald-400' :
                    isProvisioning ? 'text-amber-400' :
                    'text-rose-400'
                  }`}>
                    {store.status}
                  </span>
                </div>
              </div>

              {/* Metadata Details */}
              <div className="mt-4 pt-4 border-t border-slate-800/80 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Namespace:</span>
                  <code className="bg-slate-950 px-2 py-0.5 rounded text-slate-300 font-mono text-[11px] border border-slate-800">
                    {store.namespace}
                  </code>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">MCP Server Slug:</span>
                  <code className="text-indigo-400 font-mono text-[11px]">
                    {store.mcp_server_slug || `store_${store.slug}`}
                  </code>
                </div>

                {store.store_url && (
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Storefront:</span>
                    <a
                      href={store.store_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-cyan-400 hover:text-cyan-300 flex items-center space-x-1 font-mono text-[11px]"
                    >
                      <span>Visit Store</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                )}

                {store.error_reason && (
                  <div className="bg-rose-950/40 border border-rose-900/60 rounded-lg p-2.5 text-rose-300 text-[11px] mt-2">
                    {store.error_reason}
                  </div>
                )}
              </div>

              {/* Bottom Actions */}
              <div className="mt-4 pt-4 border-t border-slate-800/60 flex items-center justify-between text-xs">
                <span className="text-[11px] text-slate-500">
                  Provisioned: {new Date(store.created_at).toLocaleDateString()}
                </span>

                <div className="flex items-center space-x-2">
                  {store.store_url && (
                    <a
                      href={`${store.store_url}/wp-admin`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] transition-colors"
                    >
                      WP-Admin
                    </a>
                  )}

                  <button
                    onClick={() => handleDelete(store)}
                    className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 transition-colors"
                    title="Teardown Store Namespace"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}

        {stores.length === 0 && !loading && (
          <div className="col-span-full text-center py-12 bg-slate-900/40 border border-dashed border-slate-800 rounded-2xl">
            <Store className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <h4 className="text-sm font-semibold text-slate-300">No stores provisioned yet</h4>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              Click &quot;Create Store&quot; above to launch an isolated WooCommerce tenant with dedicated MariaDB and MCP pod.
            </p>
          </div>
        )}
      </div>

      {/* Create Store Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl">
            <h3 className="text-lg font-bold text-white">Provision New WooCommerce Store</h3>
            <p className="text-xs text-slate-400 mt-1">
              Deploys dedicated namespace, MariaDB, WordPress, and woocommerce-mcp pod in Kubernetes.
            </p>

            {error && (
              <div className="bg-rose-950/50 border border-rose-900 text-rose-300 text-xs rounded-xl p-3 mt-4">
                {error}
              </div>
            )}

            <form onSubmit={handleCreate} className="space-y-4 mt-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Store Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. European Audio Gear"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    if (!slug) {
                      setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 20));
                    }
                  }}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Store Slug (Subdomain & Namespace)</label>
                <input
                  type="text"
                  required
                  pattern="^[a-z0-9-]{3,20}$"
                  placeholder="e.g. audio-gear"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value.toLowerCase())}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-amber-500"
                />
                <span className="text-[10px] text-slate-500 mt-1 block">
                  Namespace: <code className="text-amber-400 font-mono">urumi-store-{slug || 'slug'}</code>
                </span>
              </div>

              <div className="bg-slate-950/80 border border-slate-800/80 rounded-xl p-3 text-[11px] text-slate-400 space-y-1">
                <span className="font-semibold text-slate-300 block mb-1">Auto-Configured Resources:</span>
                <div>• Dedicated Secret (Random DB pass, WC keys, MCP token)</div>
                <div>• ResourceQuota (1 CPU req / 2 CPU limit, 1Gi req / 2Gi limit)</div>
                <div>• Zero-Trust NetworkPolicy (isolates tenant cross-traffic)</div>
                <div>• MCP Tool Prefix: <code className="text-indigo-400 font-mono">store_{slug || 'slug'}__*</code></div>
              </div>

              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-xl text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="bg-amber-600 hover:bg-amber-500 text-white font-medium px-4 py-2 rounded-xl shadow-lg shadow-amber-600/30"
                >
                  {submitting ? 'Provisioning...' : 'Provision Store'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
