import React, { useState, useEffect } from 'react';
import { RefreshCw, ShieldCheck, Clock, Filter } from 'lucide-react';
import { api } from '../api';
import { AuditLog, AuditIntegrity } from '../types';

export const AuditLogTab: React.FC = () => {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedOutcome, setSelectedOutcome] = useState<string>('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [integrityResult, setIntegrityResult] = useState<AuditIntegrity | null>(null);
  const [inspectedLog, setInspectedLog] = useState<AuditLog | null>(null);

  const fetchLogs = async () => {
    try {
      const data = await api.getAuditLogs({ limit: 100, outcome: selectedOutcome || undefined });
      setLogs(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch audit logs');
    }
  };

  const handleVerifyIntegrity = async () => {
    setVerifying(true);
    try {
      const res = await api.verifyAuditIntegrity();
      setIntegrityResult(res);
    } catch (err: any) {
      alert(`Integrity verification failed: ${err.message}`);
    } finally {
      setVerifying(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    fetchLogs().finally(() => setLoading(false));
  }, [selectedOutcome]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => fetchLogs(), 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, selectedOutcome]);

  const outcomeConfig: Record<string, { label: string; cls: string }> = {
    SUCCESS:              { label: 'SUCCESS',      cls: 'badge-emerald' },
    REJECTED_REVOKED_KEY: { label: 'REVOKED',      cls: 'badge-rose' },
    REJECTED_FORBIDDEN:   { label: 'FORBIDDEN',    cls: 'badge-amber' },
    ERROR:                { label: 'ERROR',         cls: 'badge-rose' },
  };

  const getOutcomeBadge = (outcome: string) => {
    const cfg = outcomeConfig[outcome] || { label: outcome || 'ERROR', cls: 'badge-rose' };
    return (
      <span className={`px-2 py-0.5 rounded-lg text-[10px] font-mono font-bold ${cfg.cls}`}>
        {cfg.label}
      </span>
    );
  };

  return (
    <div className="space-y-6 animate-fadeIn">

      {/* Header */}
      <div className="card-raised overflow-hidden">
        <div className="h-1 w-full bg-gradient-to-r from-violet-500 via-indigo-500 to-blue-500" />
        <div className="p-6">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-violet-50 border border-violet-100 flex items-center justify-center">
                <ShieldCheck className="w-5 h-5 text-violet-600" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-slate-800">Tamper-Evident Audit Trail</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Every tool invocation is cryptographically chained via SHA-256 blocks with parameter redaction.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {/* Verify Chain */}
              <button
                onClick={handleVerifyIntegrity}
                disabled={verifying}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                  integrityResult?.intact
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100'
                    : integrityResult && !integrityResult.intact
                    ? 'bg-rose-50 border-rose-200 text-rose-700 hover:bg-rose-100'
                    : 'bg-gradient-to-r from-violet-600 to-indigo-600 text-white border-transparent shadow-md shadow-violet-200 hover:from-violet-700 hover:to-indigo-700'
                }`}
              >
                <svg className={`w-4 h-4 ${verifying ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                {verifying ? 'Verifying...' : integrityResult
                  ? integrityResult.intact
                    ? `✓ Intact (${integrityResult.entries_checked} verified)`
                    : `⚠ Broken at #${integrityResult.broken_at_id}`
                  : 'Verify Hash Chain'}
              </button>

              {/* Auto refresh */}
              <button
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs border font-medium transition-colors cursor-pointer ${
                  autoRefresh ? 'bg-indigo-50 border-indigo-200 text-indigo-700' : 'bg-slate-100 border-slate-200 text-slate-500'
                }`}
              >
                <span className={`w-2 h-2 rounded-full ${autoRefresh ? 'bg-indigo-500 animate-pulse' : 'bg-slate-400'}`} />
                {autoRefresh ? 'Live (5s)' : 'Paused'}
              </button>

              <button onClick={fetchLogs}
                className="p-2 text-slate-500 hover:text-indigo-600 bg-slate-100 hover:bg-indigo-50 rounded-xl border border-slate-200 hover:border-indigo-200 cursor-pointer transition-colors"
                title="Refresh">
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-indigo-500' : ''}`} />
              </button>
            </div>
          </div>

          {/* Filter chips */}
          <div className="flex items-center gap-2 mt-5 pt-4 border-t border-slate-100 overflow-x-auto">
            <span className="text-xs text-slate-500 font-medium flex items-center gap-1 shrink-0">
              <Filter className="w-3.5 h-3.5" /> Outcome:
            </span>
            {['', 'SUCCESS', 'REJECTED_REVOKED_KEY', 'REJECTED_FORBIDDEN', 'ERROR'].map((outcome) => (
              <button
                key={outcome}
                onClick={() => setSelectedOutcome(outcome)}
                className={`px-3 py-1 rounded-full font-mono text-[11px] whitespace-nowrap transition-all cursor-pointer font-semibold ${
                  selectedOutcome === outcome
                    ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-200'
                    : 'bg-slate-100 text-slate-500 hover:text-slate-700 border border-slate-200 hover:border-slate-300'
                }`}
              >
                {outcome === '' ? 'ALL' : outcome.replace('REJECTED_', '')}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 text-xs p-3 rounded-xl flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-rose-500 hover:text-rose-700 font-bold text-base leading-none">×</button>
        </div>
      )}

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 font-semibold text-[11px] uppercase tracking-wider border-b border-slate-200">
              <tr>
                <th className="py-3 px-4">Time</th>
                <th className="py-3 px-4">User & Role</th>
                <th className="py-3 px-4">Auth Source</th>
                <th className="py-3 px-4">Tool Invoked</th>
                <th className="py-3 px-4">Outcome</th>
                <th className="py-3 px-4">
                  <span className="flex items-center gap-1"><Clock className="w-3 h-3" />Latency</span>
                </th>
                <th className="py-3 px-4 font-mono">SHA-256 Hash</th>
                <th className="py-3 px-4 text-right">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-14 text-center text-slate-400 text-sm">
                    {loading ? (
                      <span className="flex items-center justify-center gap-2">
                        <RefreshCw className="w-4 h-4 animate-spin text-indigo-400" /> Loading audit records...
                      </span>
                    ) : 'No audit entries match the current filter.'}
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50 transition-colors">
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium text-slate-700">{log.user_email || 'anonymous'}</span>
                        {log.user_role && (
                          <span className={`px-1.5 py-0.5 rounded-md text-[9px] font-bold uppercase ${
                            log.user_role === 'admin' ? 'badge-indigo' : 'badge-emerald'
                          }`}>
                            {log.user_role}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px]">
                      {log.auth_method === 'api_key' ? (
                        <span className="text-indigo-600 flex items-center gap-1">🔑 API Key</span>
                      ) : (
                        <span className="text-violet-600 flex items-center gap-1">💬 Chat</span>
                      )}
                    </td>
                    <td className="py-3 px-4 font-mono">
                      <span className="text-slate-400">{log.server_slug}__</span>
                      <span className="text-slate-700 font-semibold">{log.tool_name}</span>
                    </td>
                    <td className="py-3 px-4">{getOutcomeBadge(log.outcome)}</td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-600">{log.duration_ms.toFixed(1)} ms</td>
                    <td className="py-3 px-4 font-mono text-[10px] text-slate-400">
                      {log.entry_hash ? `${log.entry_hash.substring(0, 10)}…` : '—'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => setInspectedLog(log)}
                        className="px-2.5 py-1 text-[11px] bg-slate-100 hover:bg-indigo-50 hover:text-indigo-700 text-slate-600 border border-slate-200 hover:border-indigo-200 rounded-lg transition-all cursor-pointer"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Inspect Modal */}
      {inspectedLog && (
        <div className="fixed inset-0 z-50 bg-slate-900/30 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-2xl w-full p-6 shadow-2xl shadow-slate-200/50 space-y-5 animate-fadeIn">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-800 flex items-center gap-2">
                🔍 Audit Entry #{inspectedLog.id}
              </h3>
              <button onClick={() => setInspectedLog(null)} className="text-slate-400 hover:text-slate-700 font-bold text-lg leading-none">✕</button>
            </div>

            <div className="grid grid-cols-2 gap-4 text-xs">
              <div className="bg-slate-50 border border-slate-100 p-4 rounded-xl space-y-2">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">Invocation</span>
                {[
                  ['Tool', `${inspectedLog.server_slug}__${inspectedLog.tool_name}`],
                  ['Outcome', inspectedLog.outcome],
                  ['Duration', `${inspectedLog.duration_ms} ms`],
                  ['Timestamp', new Date(inspectedLog.timestamp).toISOString()],
                ].map(([k, v]) => (
                  <p key={k} className="text-slate-600"><span className="font-semibold text-slate-700">{k}:</span> {v}</p>
                ))}
              </div>
              <div className="bg-slate-50 border border-slate-100 p-4 rounded-xl space-y-2">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">Actor</span>
                {[
                  ['Email', inspectedLog.user_email || 'anonymous'],
                  ['Role', inspectedLog.user_role || 'none'],
                  ['Auth', inspectedLog.auth_method],
                ].map(([k, v]) => (
                  <p key={k} className="text-slate-600"><span className="font-semibold text-slate-700">{k}:</span> {v}</p>
                ))}
              </div>
            </div>

            <div>
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-2">
                Arguments (sensitive fields redacted)
              </span>
              <pre className="bg-slate-800 p-3 rounded-xl text-xs font-mono text-emerald-300 border border-slate-700 overflow-x-auto max-h-40">
                {JSON.stringify(inspectedLog.arguments_redacted || {}, null, 2)}
              </pre>
            </div>

            <div className="bg-slate-50 border border-slate-100 p-4 rounded-xl font-mono text-[11px] space-y-2">
              <div>
                <span className="text-slate-500 block mb-0.5 uppercase text-[10px] font-bold tracking-wider">Previous Entry SHA-256:</span>
                <span className="text-slate-600 break-all">{inspectedLog.prev_hash || '0000…0000 (GENESIS BLOCK)'}</span>
              </div>
              <div className="pt-2 border-t border-slate-200">
                <span className="text-slate-500 block mb-0.5 uppercase text-[10px] font-bold tracking-wider">This Entry SHA-256:</span>
                <span className="text-indigo-700 break-all font-bold">{inspectedLog.entry_hash}</span>
              </div>
            </div>

            {inspectedLog.error_message && (
              <div className="bg-rose-50 border border-rose-200 p-3 rounded-xl text-xs text-rose-700">
                <strong className="block text-rose-800 mb-1">Error Payload:</strong>
                {inspectedLog.error_message}
              </div>
            )}

            <div className="flex justify-end pt-2 border-t border-slate-100">
              <button onClick={() => setInspectedLog(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-xl cursor-pointer transition-colors">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
