import React, { useState, useRef, useEffect } from 'react';
import {
  Send, Bot, User as UserIcon, Wrench, ChevronDown, ChevronRight,
  Sparkles, CheckCircle2, Play, Cpu
} from 'lucide-react';
import { User, ChatMessage, ToolExecutionPill } from '../types';
import { api } from '../api';

interface ChatTabProps {
  currentUser: User | null;
}

export const ChatTab: React.FC<ChatTabProps> = ({ currentUser }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: `Hello! I am your Autonomous Team MCP Assistant. I execute tool pipelines across all registered WooCommerce stores, analytics engines, and ops notifiers — authenticated as **${currentUser?.email || 'User'}** (${currentUser?.role || 'member'}).\n\nTry one of the quick prompts below to test multi-MCP orchestration!`,
      timestamp: new Date().toLocaleTimeString(),
    }
  ]);
  const [inputPrompt, setInputPrompt] = useState('');
  const [sending, setSending] = useState(false);
  const [expandedPill, setExpandedPill] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const quickPrompts = [
    { title: 'DoD Pipeline',        badge: 'Woo + Promos + Ops', prompt: "Fetch today's WooCommerce orders, calculate revenue metrics, and send a summary alert to Ops Notifier" },
    { title: 'Create Product',      badge: 'Admin only',          prompt: "Create a product named 'Urumi Kubernetes Hoodie' priced at $49.99" },
    { title: "Today's Orders",      badge: 'WooCommerce',         prompt: "What orders came in today on the WooCommerce store?" },
    { title: 'Multi-Store Compare', badge: 'Bonus',               prompt: "Compare today's orders across all provisioned stores" },
  ];

  const handleSend = async (textToSend?: string) => {
    const text = textToSend || inputPrompt;
    if (!text.trim() || sending) return;
    const userMsg: ChatMessage = { id: `user-${Date.now()}`, role: 'user', content: text, timestamp: new Date().toLocaleTimeString() };
    setMessages((prev) => [...prev, userMsg]);
    setInputPrompt('');
    setSending(true);
    try {
      const history = [...messages, userMsg].map((m) => ({ role: m.role, content: m.content }));
      const res = await api.sendChat(history);
      setMessages((prev) => [...prev, {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: res.message.content || 'Action executed successfully.',
        timestamp: new Date().toLocaleTimeString(),
        tool_execution_trace: res.tool_execution_trace,
      }]);
    } catch (err: any) {
      setMessages((prev) => [...prev, {
        id: `err-${Date.now()}`, role: 'system', content: `Error: ${err.message}`, timestamp: new Date().toLocaleTimeString(),
      }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-14rem)] max-w-5xl mx-auto card-raised overflow-hidden animate-fadeIn">

      {/* Chat Header */}
      <div className="h-1 w-full bg-gradient-to-r from-indigo-500 via-violet-500 to-blue-500" />
      <div className="p-4 border-b border-slate-100 bg-white flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center">
            <Bot className="w-4 h-4 text-indigo-600" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
              Autonomous MCP Agent
              <span className="text-[10px] px-2 py-0.5 rounded-full badge-emerald font-semibold">Online · RBAC Active</span>
            </h3>
            <span className="text-[11px] text-slate-500">
              Authenticated as <span className="font-semibold text-slate-700">{currentUser?.email}</span>
              <span className={`ml-1.5 font-bold text-[10px] uppercase ${currentUser?.role === 'admin' ? 'text-indigo-600' : 'text-emerald-600'}`}>
                ({currentUser?.role})
              </span>
            </span>
          </div>
        </div>
        <div className="hidden sm:flex items-center gap-1.5 text-[11px] text-slate-500 bg-slate-50 border border-slate-200 px-2.5 py-1 rounded-lg font-mono">
          <Cpu className="w-3 h-3 text-indigo-500" />
          POST /api/chat
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5 bg-slate-50/50">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex items-start gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
          >
            <div className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 text-sm ${
              msg.role === 'user'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200'
                : msg.role === 'system'
                ? 'bg-rose-50 text-rose-500 border border-rose-200'
                : 'bg-white text-indigo-600 border border-indigo-100 shadow-sm'
            }`}>
              {msg.role === 'user' ? <UserIcon className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
            </div>

            <div className={`max-w-2xl rounded-2xl p-4 text-xs shadow-sm ${
              msg.role === 'user'
                ? 'bg-indigo-600 text-white'
                : msg.role === 'system'
                ? 'bg-rose-50 border border-rose-200 text-rose-700'
                : 'bg-white border border-slate-200 text-slate-700'
            }`}>
              {/* Tool pills */}
              {msg.tool_execution_trace && msg.tool_execution_trace.length > 0 && (
                <div className="mb-3 space-y-2">
                  <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider flex items-center gap-1.5">
                    <Wrench className="w-3 h-3 text-indigo-500" />
                    Tool Calls ({msg.tool_execution_trace.length}):
                  </span>
                  <div className="space-y-1.5">
                    {msg.tool_execution_trace.map((pill: ToolExecutionPill, idx: number) => {
                      const pillKey = `${msg.id}-${idx}`;
                      const isExpandedPill = expandedPill === pillKey;
                      const [serverSlug, toolName] = pill.tool.includes('__') ? pill.tool.split('__') : ['gateway', pill.tool];
                      return (
                        <div key={pillKey} className="bg-slate-50 border border-slate-200 rounded-xl overflow-hidden text-[11px]">
                          <button
                            onClick={() => setExpandedPill(isExpandedPill ? null : pillKey)}
                            className="w-full px-3 py-2 flex items-center justify-between text-left hover:bg-slate-100 transition-colors"
                          >
                            <div className="flex items-center gap-2">
                              <span className="px-1.5 py-0.5 rounded-lg bg-indigo-50 text-indigo-700 font-mono font-bold border border-indigo-100 text-[10px]">
                                {serverSlug}
                              </span>
                              <span className="font-mono text-slate-700 font-semibold">{toolName}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="flex items-center gap-1 text-[10px] text-emerald-600 font-semibold">
                                <CheckCircle2 className="w-3 h-3" /> OK
                              </span>
                              {isExpandedPill ? <ChevronDown className="w-3.5 h-3.5 text-slate-400" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-400" />}
                            </div>
                          </button>
                          {isExpandedPill && (
                            <div className="p-3 bg-slate-800 text-[10px] space-y-2">
                              <div>
                                <span className="text-slate-400 block mb-0.5">// Arguments:</span>
                                <pre className="text-indigo-300 overflow-x-auto">{JSON.stringify(pill.arguments, null, 2)}</pre>
                              </div>
                              <div>
                                <span className="text-slate-400 block mb-0.5">// Response:</span>
                                <pre className="text-emerald-300 overflow-x-auto max-h-40">
                                  {typeof pill.result === 'string' ? pill.result : JSON.stringify(pill.result, null, 2)}
                                </pre>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
              <div className="mt-2 text-[10px] opacity-60 text-right">{msg.timestamp}</div>
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-white border border-indigo-100 shadow-sm flex items-center justify-center animate-pulse">
              <Bot className="w-4 h-4 text-indigo-500" />
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm flex items-center gap-2 text-xs text-slate-500">
              <span className="w-2 h-2 rounded-full bg-indigo-500 animate-ping" />
              Reasoning & executing tool pipeline...
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Quick Prompts */}
      <div className="px-4 py-2.5 bg-white border-t border-slate-100 overflow-x-auto flex items-center gap-2">
        <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider shrink-0 flex items-center gap-1">
          <Sparkles className="w-3 h-3 text-amber-500" /> Quick:
        </span>
        {quickPrompts.map((qp, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(qp.prompt)}
            disabled={sending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-50 hover:bg-indigo-50 border border-slate-200 hover:border-indigo-200 text-slate-600 hover:text-indigo-700 text-xs whitespace-nowrap transition-all shrink-0 disabled:opacity-50"
          >
            <Play className="w-2.5 h-2.5 text-indigo-500" />
            <span className="font-medium">{qp.title}</span>
            <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-white border border-slate-200 text-slate-400 font-mono">{qp.badge}</span>
          </button>
        ))}
      </div>

      {/* Input Bar */}
      <div className="p-4 border-t border-slate-100 bg-white">
        <form onSubmit={(e) => { e.preventDefault(); handleSend(); }} className="flex items-center gap-2">
          <input
            type="text"
            value={inputPrompt}
            onChange={(e) => setInputPrompt(e.target.value)}
            disabled={sending}
            placeholder="Ask agent to query orders, create products, run analytics, or send alerts..."
            className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-xs text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-300 transition-all"
          />
          <button
            type="submit"
            disabled={sending || !inputPrompt.trim()}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white p-3 rounded-xl shadow-md shadow-indigo-200 transition-all shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
};
