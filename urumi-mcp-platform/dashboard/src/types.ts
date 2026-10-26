export type UserRole = 'admin' | 'member';

export interface User {
  id: number;
  email: string;
  name?: string;
  role: UserRole;
  created_at: string;
}

export interface ApiKey {
  id: number;
  name: string;
  key_prefix: string;
  revoked_at?: string | null;
  created_at: string;
  last_used_at?: string | null;
}

export interface ApiKeyCreatedResponse {
  id: number;
  name: string;
  key_prefix: string;
  raw_api_key: string;
  created_at: string;
}

export interface McpTool {
  name: string;
  description?: string;
  inputSchema?: Record<string, any>;
}

export type ServerStatus = 'Connected' | 'Unreachable' | 'Disabled';

export interface UpstreamServer {
  id: number;
  name: string;
  slug: string;
  url: string;
  auth_header_name: string;
  enabled: boolean;
  is_hosted: boolean;
  container_image?: string | null;
  status: ServerStatus;
  last_error?: string | null;
  latency_ms: number;
  total_calls: number;
  failed_calls: number;
  cached_tools: McpTool[];
  last_health_check?: string | null;
  created_at: string;
}

export type StoreStatus = 'Provisioning' | 'Ready' | 'Failed' | 'Deleting';

export interface ProvisionedStore {
  id: number;
  name: string;
  slug: string;
  namespace: string;
  owner_user_id: number;
  status: StoreStatus;
  store_url?: string | null;
  mcp_server_id?: number | null;
  mcp_server_slug?: string | null;
  error_reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditLog {
  id: number;
  timestamp: string;
  user_id?: number | null;
  user_email?: string | null;
  user_role?: string | null;
  auth_method: string;
  server_slug?: string | null;
  tool_name?: string | null;
  arguments_redacted?: Record<string, any> | null;
  duration_ms: number;
  outcome: string;
  error_message?: string | null;
  prev_hash?: string | null;
  entry_hash: string;
}

export interface AuditIntegrity {
  intact: boolean;
  entries_checked: number;
  latest_hash?: string;
  broken_at_id?: number;
  error?: string;
  message?: string;
}

export interface ToolExecutionPill {
  tool: string;
  arguments: Record<string, any>;
  result: any;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  tool_execution_trace?: ToolExecutionPill[];
}
