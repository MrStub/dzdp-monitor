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
  group_key: string;
  group_name?: string;
  last_state: "IN_STOCK" | "SOLD_OUT" | "UNKNOWN" | string;
  last_sold_out?: boolean;
  last_title: string;
  last_change_ts: string;
  last_error_text: string;
  last_error_streak: number;
  fail_count: number;
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
