export type NoticeType = "success" | "error";

export interface Summary {
  total_targets: number;
  in_stock: number;
  sold_out: number;
  unknown: number;
  error_targets: number;
}

export interface TargetItem {
  index: number;
  name: string;
  url: string;
  activity_id: string;
  enabled: boolean;
  group_keys: string[];
  group_key: string;
  group_names?: string[];
  group_name?: string;
  last_state: "IN_STOCK" | "SOLD_OUT" | "UNKNOWN" | string;
  last_sold_out?: boolean;
  last_title: string;
  last_change_ts: string;
  last_error_text: string;
  last_error_streak: number;
  fail_count: number;
  disabled_reason: string;
  consecutive_null_brief_count: number;
}

export interface NotifyGroup {
  key: string;
  name: string;
  webhook_masked?: string;
  webhook_configured?: boolean;
  is_default?: boolean;
}

export interface PollSettings {
  interval_seconds: number;
}

export interface ProxyConfig {
  enabled: boolean;
  provider: string;
  request_method: "GET" | "POST" | string;
  api_url: string;
  api_key?: string;
  api_key_header: string;
  api_key_configured?: boolean;
  extra_headers: Record<string, string>;
  query_params: Record<string, string>;
  request_body: Record<string, unknown>;
  response_data_path: string;
  response_fields: Record<string, string>;
  cache_seconds: number;
  timeout_seconds: number;
  sticky_mode: "shared" | "per_target" | string;
  verify_ssl: boolean;
}

export interface AdminApiInfo {
  auth_token_configured: boolean;
}

export interface Dashboard {
  generated_at?: string;
  summary: Summary;
  targets: TargetItem[];
  notify_groups: NotifyGroup[];
  poll: PollSettings;
  proxy: ProxyConfig;
  admin_api: AdminApiInfo;
}

export type PermissionKey =
  | "targets_read"
  | "targets_create"
  | "targets_update"
  | "targets_delete"
  | "webhook_manage"
  | "poll_manage"
  | "proxy_manage";

export type UserPermissions = Record<PermissionKey, boolean>;

export interface AuthUser {
  id: number | null;
  username: string;
  is_admin: boolean;
}

export interface AuthMeResponse {
  user: AuthUser;
  permissions: UserPermissions;
  legacy_token?: boolean;
}

export interface AuthLoginResponse {
  token: string;
  token_type: string;
  expires_at: string;
  user: AuthUser;
  permissions: UserPermissions;
}

export interface UserItem {
  id: number;
  username: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string;
  permissions: UserPermissions;
}
