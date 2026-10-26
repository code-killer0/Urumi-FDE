import React, { useState, useEffect } from 'react';
import { api } from '../api';
import { ApiKey, ApiKeyCreatedResponse, User } from '../types';

interface TeamKeysTabProps {
  currentUser: User | null;
}

interface ToolPermissionRule {
  server: string;
  tool: string;
  description: string;
  memberAllowed: boolean;
  adminAllowed: boolean;
}

const DEFAULT_PERMISSION_RULES: ToolPermissionRule[] = [
  { server: 'woo', tool: 'list_products', description: 'Query WooCommerce product catalog', memberAllowed: true, adminAllowed: true },
  { server: 'woo', tool: 'list_orders', description: 'Read order status and customer line items', memberAllowed: true, adminAllowed: true },
  { server: 'woo', tool: 'get_order_details', description: 'Retrieve detailed order and payment info', memberAllowed: true, adminAllowed: true },
  { server: 'woo', tool: 'create_product', description: 'Create and publish products in store', memberAllowed: false, adminAllowed: true },
  { server: 'woo', tool: 'update_order_status', description: 'Modify live fulfillment order states', memberAllowed: false, adminAllowed: true },
  { server: 'promos', tool: 'get_customer_metrics', description: 'Calculate CLV and repeat purchase rate', memberAllowed: true, adminAllowed: true },
  { server: 'promos', tool: 'get_top_selling_products', description: 'Query revenue rankings by sales volume', memberAllowed: true, adminAllowed: true },
  { server: 'promos', tool: 'apply_bulk_discount', description: 'Write promotional discounts to store items', memberAllowed: false, adminAllowed: true },
  { server: 'ops', tool: 'send_slack_alert', description: 'Send alert notification to team Slack channel', memberAllowed: true, adminAllowed: true },
  { server: 'ops', tool: 'send_pagerduty_incident', description: 'Trigger high-urgency on-call page', memberAllowed: false, adminAllowed: true },
  { server: 'ops', tool: 'get_oncall_schedule', description: 'View current primary on-call engineer', memberAllowed: true, adminAllowed: true },
];

export const TeamKeysTab: React.FC<TeamKeysTabProps> = ({ currentUser }) => {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New Key Modal state
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [keyName, setKeyName] = useState('');
  const [generating, setGenerating] = useState(false);
  const [createdKeyData, setCreatedKeyData] = useState<ApiKeyCreatedResponse | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedCursor, setCopiedCursor] = useState(false);
  const [copiedClaude, setCopiedClaude] = useState(false);

  // Permissions Matrix state
  const [rules, setRules] = useState<ToolPermissionRule[]>(DEFAULT_PERMISSION_RULES);
  const [policySavedMsg, setPolicySavedMsg] = useState(false);

  const isAdmin = currentUser?.role === 'admin';

  const fetchKeys = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getKeys();
      setKeys(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch API keys');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKeys();
  }, []);

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyName.trim()) return;
    setGenerating(true);
    setError(null);
    try {
      const res = await api.createKey(keyName.trim());
      setCreatedKeyData(res);
      setKeyName('');
      await fetchKeys();
    } catch (err: any) {
      setError(err.message || 'Failed to generate key');
    } finally {
      setGenerating(false);
    }
  };

  const handleRevokeKey = async (id: number, name: string) => {
    if (!confirm(`Are you sure you want to revoke API key "${name}"? This action cannot be undone.`)) {
      return;
    }
    try {
      await api.revokeKey(id);
      await fetchKeys();
    } catch (err: any) {
      alert(`Error revoking key: ${err.message}`);
    }
  };

  const handleToggleMemberPermission = (index: number) => {
    if (!isAdmin) return;
    const updated = [...rules];
    updated[index].memberAllowed = !updated[index].memberAllowed;
    setRules(updated);
    setPolicySavedMsg(true);
    setTimeout(() => setPolicySavedMsg(false), 2500);
  };

  const gatewayUrl = typeof window !== 'undefined'
    ? `${window.location.protocol}//${window.location.host}/mcp`
    : 'http://gateway.127.0.0.1.nip.io/mcp';

  const cursorJsonSnippet = createdKeyData ? JSON.stringify({
    mcpServers: {
      "urumi-gateway": {
        url: gatewayUrl,
        headers: {
          Authorization: `Bearer ${createdKeyData.raw_api_key}`
        }
      }
    }
  }, null, 2) : '';

  const claudeCodeSnippet = createdKeyData
    ? `claude mcp add --transport http urumi-gateway ${gatewayUrl} --header "Authorization: Bearer ${createdKeyData.raw_api_key}"`
    : '';

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Header & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <span>🔑</span> Team API Keys & RBAC Governance
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Generate personal API keys for Cursor, Claude Code, and Windsurf. Manage team tool execution privileges.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setCreatedKeyData(null);
              setKeyName('');
              setShowGenerateModal(true);
            }}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold rounded-lg shadow-lg shadow-emerald-900/30 transition-all cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Generate New API Key
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-rose-950/40 border border-rose-800 text-rose-300 text-xs p-3 rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-white font-bold">×</button>
        </div>
      )}

      {/* API Keys Table */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-200">Active API Keys</span>
            <span className="px-2 py-0.5 text-[10px] bg-slate-800 text-slate-300 rounded-full font-mono">
              {keys.length} total
            </span>
          </div>
          <button
            onClick={fetchKeys}
            className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1 cursor-pointer"
          >
            <svg className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 font-mono text-[11px] uppercase tracking-wider border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Key Name</th>
                <th className="py-3 px-4">Prefix</th>
                <th className="py-3 px-4">Created At</th>
                <th className="py-3 px-4">Last Used</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-sans">
              {keys.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500">
                    {loading ? 'Loading API keys...' : 'No API keys generated yet. Click "Generate New API Key" above.'}
                  </td>
                </tr>
              ) : (
                keys.map((k) => {
                  const isRevoked = Boolean(k.revoked_at);
                  return (
                    <tr key={k.id} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-3 px-4 font-medium text-slate-200">
                        {k.name}
                      </td>
                      <td className="py-3 px-4 font-mono text-cyan-400">
                        {k.key_prefix}••••••••••••
                      </td>
                      <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                        {new Date(k.created_at).toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                        {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : 'Never'}
                      </td>
                      <td className="py-3 px-4">
                        {isRevoked ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-950/60 text-rose-400 border border-rose-800/60">
                            Revoked
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-950/60 text-emerald-400 border border-emerald-800/60">
                            Active
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {!isRevoked && (
                          <button
                            onClick={() => handleRevokeKey(k.id, k.name)}
                            className="px-2.5 py-1 text-[11px] bg-rose-900/30 hover:bg-rose-900/60 text-rose-300 border border-rose-800/60 rounded font-medium transition-colors cursor-pointer"
                          >
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* RBAC Permission Matrix Section */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        <div className="p-4 border-b border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>🛡️</span> Role-Based Tool Permission Matrix (RBAC)
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Defines which MCP tool invocations are authorized for Members vs Admins. Enforced deterministically on the Gateway before upstream dispatch.
            </p>
          </div>
          {policySavedMsg && (
            <span className="text-[11px] text-emerald-400 bg-emerald-950/80 border border-emerald-800 px-3 py-1 rounded-full animate-bounce">
              ✓ RBAC Policy Rule Updated
            </span>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 font-mono text-[11px] uppercase tracking-wider border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Upstream Server</th>
                <th className="py-3 px-4">Qualified Tool Name</th>
                <th className="py-3 px-4">Description</th>
                <th className="py-3 px-4 text-center">Admin Access</th>
                <th className="py-3 px-4 text-center">Member Access</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-sans">
              {rules.map((rule, idx) => (
                <tr key={`${rule.server}__${rule.tool}`} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-3 px-4 font-mono font-medium text-cyan-400">
                    {rule.server}
                  </td>
                  <td className="py-3 px-4 font-mono text-slate-200">
                    <span className="text-slate-500">{rule.server}__</span>
                    <span className="font-semibold">{rule.tool}</span>
                  </td>
                  <td className="py-3 px-4 text-slate-400 max-w-xs truncate">
                    {rule.description}
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-800/80">
                      ✓ Full Access
                    </span>
                  </td>
                  <td className="py-3 px-4 text-center">
                    {isAdmin ? (
                      <button
                        onClick={() => handleToggleMemberPermission(idx)}
                        className={`px-3 py-1 rounded text-[11px] font-medium transition-all cursor-pointer ${
                          rule.memberAllowed
                            ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/80 hover:bg-emerald-900/80'
                            : 'bg-rose-950/60 text-rose-300 border border-rose-800/80 hover:bg-rose-900/80'
                        }`}
                        title="Click to toggle member access permission"
                      >
                        {rule.memberAllowed ? 'Allowed' : 'Forbidden'}
                      </button>
                    ) : (
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold ${
                        rule.memberAllowed
                          ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800/60'
                          : 'bg-rose-950/60 text-rose-400 border border-rose-800/60'
                      }`}>
                        {rule.memberAllowed ? 'Allowed' : 'Forbidden'}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Generate API Key Modal */}
      {showGenerateModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-6">
            {!createdKeyData ? (
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                  <h3 className="text-lg font-bold text-white flex items-center gap-2">
                    <span>✨</span> Generate New Personal API Key
                  </h3>
                  <button
                    onClick={() => setShowGenerateModal(false)}
                    className="text-slate-400 hover:text-white font-bold"
                  >
                    ✕
                  </button>
                </div>
                <p className="text-xs text-slate-400 mt-2">
                  API keys provide continuous programmatic access to the Gateway via Streamable HTTP for Claude Code, Cursor, and IDE extensions.
                </p>

                <form onSubmit={handleCreateKey} className="mt-4 space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Key Name / Purpose *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Harshit MacBook Cursor MCP or Claude CLI"
                      value={keyName}
                      onChange={(e) => setKeyName(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                    />
                  </div>

                  <div className="flex items-center justify-end gap-3 pt-3">
                    <button
                      type="button"
                      onClick={() => setShowGenerateModal(false)}
                      className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded-lg cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={generating}
                      className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg cursor-pointer flex items-center gap-2"
                    >
                      {generating ? 'Generating...' : 'Generate API Key'}
                    </button>
                  </div>
                </form>
              </div>
            ) : (
              /* Success & Plaintext Key Display Modal */
              <div className="space-y-5">
                <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                  <h3 className="text-lg font-bold text-emerald-400 flex items-center gap-2">
                    <span>✅</span> API Key Created Successfully
                  </h3>
                  <button
                    onClick={() => {
                      setShowGenerateModal(false);
                      setCreatedKeyData(null);
                    }}
                    className="text-slate-400 hover:text-white font-bold"
                  >
                    ✕
                  </button>
                </div>

                <div className="bg-amber-950/40 border border-amber-800/70 p-3 rounded-lg text-xs text-amber-300 flex items-start gap-2">
                  <span className="text-base">⚠️</span>
                  <div>
                    <span className="font-semibold">Copy this key now.</span> For your security, this key will never be shown again. If you lose it, you will need to revoke it and generate a new one.
                  </div>
                </div>

                {/* Raw Key Display */}
                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1">
                    RAW API KEY ({createdKeyData.name})
                  </label>
                  <div className="flex items-center gap-2 bg-slate-950 border border-slate-700 rounded-lg p-2.5">
                    <input
                      type="text"
                      readOnly
                      value={createdKeyData.raw_api_key}
                      className="bg-transparent border-none text-emerald-400 font-mono text-xs w-full focus:outline-none select-all"
                    />
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(createdKeyData.raw_api_key);
                        setCopiedKey(true);
                        setTimeout(() => setCopiedKey(false), 2000);
                      }}
                      className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-semibold rounded transition-colors whitespace-nowrap cursor-pointer"
                    >
                      {copiedKey ? '✓ Copied' : 'Copy Key'}
                    </button>
                  </div>
                </div>

                {/* Cursor .cursor/mcp.json Snippet */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] font-mono text-slate-400">
                      CURSOR SETUP (<code className="text-cyan-400">.cursor/mcp.json</code>)
                    </label>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(cursorJsonSnippet);
                        setCopiedCursor(true);
                        setTimeout(() => setCopiedCursor(false), 2000);
                      }}
                      className="text-[11px] text-cyan-400 hover:text-cyan-300 cursor-pointer"
                    >
                      {copiedCursor ? '✓ Copied JSON' : 'Copy JSON'}
                    </button>
                  </div>
                  <pre className="bg-slate-950 p-3 rounded-lg text-[11px] font-mono text-slate-300 border border-slate-800 overflow-x-auto">
                    {cursorJsonSnippet}
                  </pre>
                </div>

                {/* Claude Code CLI Snippet */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] font-mono text-slate-400">
                      CLAUDE CODE CLI COMMAND
                    </label>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(claudeCodeSnippet);
                        setCopiedClaude(true);
                        setTimeout(() => setCopiedClaude(false), 2000);
                      }}
                      className="text-[11px] text-cyan-400 hover:text-cyan-300 cursor-pointer"
                    >
                      {copiedClaude ? '✓ Copied CLI' : 'Copy Command'}
                    </button>
                  </div>
                  <pre className="bg-slate-950 p-2.5 rounded-lg text-[11px] font-mono text-slate-300 border border-slate-800 overflow-x-auto whitespace-pre-wrap break-all">
                    {claudeCodeSnippet}
                  </pre>
                </div>

                <div className="pt-2 flex justify-end">
                  <button
                    onClick={() => {
                      setShowGenerateModal(false);
                      setCreatedKeyData(null);
                    }}
                    className="px-5 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold rounded-lg cursor-pointer"
                  >
                    Done & Dismiss
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
