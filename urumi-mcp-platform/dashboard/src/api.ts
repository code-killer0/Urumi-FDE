import {
  User, UpstreamServer, ProvisionedStore, ApiKey,
  ApiKeyCreatedResponse, AuditLog, AuditIntegrity
} from './types';

const API_BASE = '/api/v1';

class ApiClient {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem('urumi_token');
  }

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('urumi_token', token);
    } else {
      localStorage.removeItem('urumi_token');
    }
  }

  getToken(): string | null {
    return this.token;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(endpoint, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      // Don't auto-clear token if it was a revoked API key test, but notify
      const err = await response.json().catch(() => ({ detail: 'Unauthorized' }));
      throw new Error(err.detail || 'Authentication required');
    }

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
      throw new Error(err.detail || err.error?.message || `Request failed: ${response.status}`);
    }

    return response.json();
  }

  // ── Auth ──────────────────────────────────────────────────────────────────
  async login(email: string, password: string): Promise<{ access_token: string; user: User }> {
    const data = await this.request<{ access_token: string; user: User }>(`${API_BASE}/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async getMe(): Promise<User> {
    return this.request<User>(`${API_BASE}/auth/me`);
  }

  async switchUser(role: 'admin' | 'member'): Promise<{ access_token: string; user: User }> {
    const creds = role === 'admin'
      ? { email: 'admin@urumi.local', password: 'UrumiAdmin2026!' }
      : { email: 'member@urumi.local', password: 'UrumiMember2026!' };
    return this.login(creds.email, creds.password);
  }

  // ── Upstream Servers ──────────────────────────────────────────────────────
  async getServers(): Promise<UpstreamServer[]> {
    return this.request<UpstreamServer[]>(`${API_BASE}/servers`);
  }

  async createServer(payload: {
    name: string;
    slug: string;
    url?: string;
    auth_header_name?: string;
    credential?: string;
    is_hosted?: boolean;
    container_image?: string;
    env_vars?: Record<string, string>;
  }): Promise<UpstreamServer> {
    return this.request<UpstreamServer>(`${API_BASE}/servers`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async updateServer(id: number, patch: Partial<UpstreamServer>): Promise<UpstreamServer> {
    return this.request<UpstreamServer>(`${API_BASE}/servers/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
  }

  async deleteServer(id: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`${API_BASE}/servers/${id}`, {
      method: 'DELETE',
    });
  }

  async syncTools(id: number): Promise<UpstreamServer> {
    return this.request<UpstreamServer>(`${API_BASE}/servers/${id}/sync-tools`, {
      method: 'POST',
    });
  }

  // ── Provisioned Stores ────────────────────────────────────────────────────
  async getStores(): Promise<ProvisionedStore[]> {
    return this.request<ProvisionedStore[]>('/api/stores');
  }

  async createStore(payload: { name: string; slug: string }): Promise<ProvisionedStore> {
    return this.request<ProvisionedStore>('/api/stores', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async deleteStore(id: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/api/stores/${id}`, {
      method: 'DELETE',
    });
  }

  // ── API Keys ──────────────────────────────────────────────────────────────
  async getKeys(): Promise<ApiKey[]> {
    return this.request<ApiKey[]>(`${API_BASE}/keys`);
  }

  async createKey(name: string): Promise<ApiKeyCreatedResponse> {
    return this.request<ApiKeyCreatedResponse>(`${API_BASE}/keys`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  }

  async revokeKey(id: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`${API_BASE}/keys/${id}`, {
      method: 'DELETE',
    });
  }

  // ── Audit Logs ────────────────────────────────────────────────────────────
  async getAuditLogs(params?: { limit?: number; outcome?: string; server?: string }): Promise<AuditLog[]> {
    const q = new URLSearchParams();
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.outcome) q.set('outcome', params.outcome);
    if (params?.server) q.set('server', params.server);
    return this.request<AuditLog[]>(`${API_BASE}/audit?${q.toString()}`);
  }

  async verifyAuditIntegrity(): Promise<AuditIntegrity> {
    return this.request<AuditIntegrity>(`${API_BASE}/audit/verify-integrity`);
  }

  // ── Chat Agent ────────────────────────────────────────────────────────────
  async sendChat(messages: Array<{ role: string; content: string }>): Promise<{
    message: { role: string; content: string };
    tool_execution_trace: any[];
  }> {
    return this.request('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ messages }),
    });
  }

  // ── Direct MCP Protocol Endpoint ──────────────────────────────────────────
  async callMcp(payload: {
    jsonrpc: string;
    id: number | string;
    method: string;
    params?: any;
  }, scaleMode = false, apiKeyOverride?: string): Promise<any> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (apiKeyOverride) {
      headers['Authorization'] = `Bearer ${apiKeyOverride}`;
    } else if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }
    if (scaleMode) {
      headers['X-MCP-Scale-Mode'] = 'true';
    }

    const res = await fetch('/mcp', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
    return res.json();
  }
}

export const api = new ApiClient();
