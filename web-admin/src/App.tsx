import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  Activity,
  Boxes,
  Cable,
  CircleAlert,
  Link2,
  LogOut,
  Plus,
  Settings2,
  ShieldCheck,
  UserCog,
  Waves,
} from "lucide-react";
import { ApiRequestError, apiRequest, getDefaultBaseUrl } from "@/lib/api";
import type {
  AuthMeResponse,
  AuthUser,
  Dashboard,
  NoticeType,
  NotifyGroup,
  PermissionKey,
  ProxyConfig,
  TargetItem,
  UserItem,
  UserPermissions,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const DEFAULT_RESPONSE_FIELDS = {
  proxy_url: "proxy_url",
  scheme: "scheme",
  host: "host",
  port: "port",
  username: "username",
  password: "password",
};

function defaultDashboard(): Dashboard {
  return {
    summary: {
      total_targets: 0,
      in_stock: 0,
      sold_out: 0,
      unknown: 0,
      error_targets: 0,
    },
    targets: [],
    notify_groups: [],
    poll: { interval_seconds: 60 },
    proxy: {
      enabled: false,
      provider: "generic_json",
      request_method: "GET",
      api_url: "",
      api_key_header: "X-API-Key",
      api_key_configured: false,
      extra_headers: {},
      query_params: {},
      request_body: {},
      response_data_path: "",
      response_fields: { ...DEFAULT_RESPONSE_FIELDS },
      cache_seconds: 120,
      timeout_seconds: 8,
      sticky_mode: "shared",
      verify_ssl: true,
    },
    admin_api: {
      auth_token_configured: false,
    },
  };
}

function getTargetIdentity(target: TargetItem) {
  if (target.index !== undefined && target.index !== null) {
    return `index:${target.index}`;
  }
  return `fallback:${target.activity_id}:${target.name}`;
}

function isPrimitiveArrayEqual<T>(left: T[] | undefined, right: T[] | undefined) {
  if (left === right) {
    return true;
  }
  if (!left || !right || left.length !== right.length) {
    return false;
  }
  return left.every((value, index) => value === right[index]);
}

function isTargetEqual(left: TargetItem, right: TargetItem) {
  return (
    left.index === right.index &&
    left.name === right.name &&
    left.url === right.url &&
    left.activity_id === right.activity_id &&
    left.enabled === right.enabled &&
    isPrimitiveArrayEqual(left.group_keys, right.group_keys) &&
    left.group_key === right.group_key &&
    isPrimitiveArrayEqual(left.group_names, right.group_names) &&
    left.group_name === right.group_name &&
    left.last_state === right.last_state &&
    left.last_sold_out === right.last_sold_out &&
    left.last_title === right.last_title &&
    left.last_change_ts === right.last_change_ts &&
    left.last_error_text === right.last_error_text &&
    left.last_error_streak === right.last_error_streak &&
    left.fail_count === right.fail_count &&
    left.disabled_reason === right.disabled_reason &&
    left.consecutive_null_brief_count === right.consecutive_null_brief_count
  );
}

function mergeTargets(previousTargets: TargetItem[], nextTargets: TargetItem[]) {
  const previousByIdentity = new Map(
    previousTargets.map((target) => [getTargetIdentity(target), target]),
  );

  return nextTargets.map((target) => {
    const previousTarget = previousByIdentity.get(getTargetIdentity(target));
    if (!previousTarget) {
      return target;
    }
    return isTargetEqual(previousTarget, target) ? previousTarget : target;
  });
}

type Notice = {
  type: NoticeType;
  message: string;
};

function GlobalNoticeToast({ notice }: { notice: Notice }) {
  if (!notice.message) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed bottom-[13vh] left-1/2 z-[120] w-[min(calc(100vw-2rem),420px)] -translate-x-1/2 px-4">
      <div
        className={cn(
          "rounded-2xl border px-4 py-3 text-sm shadow-lg backdrop-blur",
          notice.type === "error"
            ? "border-rose-200 bg-rose-50/95 text-rose-800"
            : "border-emerald-200 bg-emerald-50/95 text-emerald-800",
        )}
      >
        {notice.message}
      </div>
    </div>
  );
}

type LoadingState = {
  dashboard: boolean;
  loginSubmit: boolean;
  targetSubmit: boolean;
  groupSubmit: boolean;
  pollSubmit: boolean;
  proxySubmit: boolean;
};

type TargetForm = {
  name: string;
  url: string;
  group_keys: string[];
  enabled: boolean;
};

type GroupForm = {
  name: string;
  key: string;
  webhook: string;
  clear_webhook: boolean;
  make_default: boolean;
};

type ProxyForm = {
  enabled: boolean;
  provider: string;
  request_method: string;
  api_url: string;
  api_key: string;
  api_key_header: string;
  extra_headers_json: string;
  query_params_json: string;
  request_body_json: string;
  response_data_path: string;
  response_fields_json: string;
  cache_seconds: number;
  timeout_seconds: number;
  sticky_mode: string;
  verify_ssl: boolean;
};

type TabId = "connection" | "targets" | "groups" | "poll" | "proxy" | "permissions";

const PERMISSION_KEYS = [
  "targets_read",
  "targets_create",
  "targets_update",
  "targets_delete",
  "webhook_manage",
  "poll_manage",
  "proxy_manage",
] as const;

type NavPermission = PermissionKey | "admin_only";

type NavItem = {
  id: TabId;
  label: string;
  icon: typeof Link2;
  hint: string;
  permission?: NavPermission;
};

const PERMISSION_LABELS: Record<PermissionKey, string> = {
  targets_read: "查看监控套餐",
  targets_create: "新增监控套餐",
  targets_update: "编辑监控套餐",
  targets_delete: "删除监控套餐",
  webhook_manage: "管理通知分组与通知地址",
  poll_manage: "管理轮询频率",
  proxy_manage: "管理代理配置",
};

const PERMISSION_DESCRIPTIONS: Record<PermissionKey, string> = {
  targets_read: "允许查看监控套餐列表与详情。",
  targets_create: "允许新增监控套餐配置。",
  targets_update: "允许修改已有监控套餐配置。",
  targets_delete: "允许删除现有监控套餐。",
  webhook_manage: "允许维护通知分组以及对应的通知地址配置。",
  poll_manage: "允许调整系统轮询频率。",
  proxy_manage: "允许维护代理服务接入与请求参数配置。",
};

const DEFAULT_OPERATOR_PERMISSIONS: UserPermissions = {
  targets_read: true,
  targets_create: true,
  targets_update: false,
  targets_delete: false,
  webhook_manage: false,
  poll_manage: false,
  proxy_manage: false,
};

const NAV_ITEMS: NavItem[] = [
  {
    id: "targets",
    label: "监控套餐",
    icon: Boxes,
    hint: "套餐增删改查",
    permission: "targets_read",
  },
  { id: "connection", label: "连接设置", icon: Link2, hint: "鉴权与连接状态" },
  {
    id: "groups",
    label: "通知分组",
    icon: Waves,
    hint: "分组与通知地址",
    permission: "webhook_manage",
  },
  {
    id: "poll",
    label: "轮询配置",
    icon: Activity,
    hint: "轮询频率",
    permission: "poll_manage",
  },
  {
    id: "proxy",
    label: "代理设置",
    icon: Settings2,
    hint: "代理池接入",
    permission: "proxy_manage",
  },
  {
    id: "permissions",
    label: "用户权限",
    icon: UserCog,
    hint: "账号与功能权限",
    permission: "admin_only",
  },
];

const API_TOKEN_STORAGE_KEY = "dzdp_api_token";
const REMEMBER_LOGIN_STORAGE_KEY = "dzdp_login_remember_v1";

function getLocalValue(key: string, fallback: string) {
  return window.localStorage.getItem(key) ?? fallback;
}

function encodeBase64(text: string) {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return window.btoa(binary);
}

function decodeBase64(text: string) {
  const binary = window.atob(text);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function readRememberedLogin() {
  const raw = window.localStorage.getItem(REMEMBER_LOGIN_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const decoded = JSON.parse(decodeBase64(raw)) as Record<string, unknown>;
    return {
      username: String(decoded.username ?? ""),
      password: String(decoded.password ?? ""),
    };
  } catch {
    window.localStorage.removeItem(REMEMBER_LOGIN_STORAGE_KEY);
    return null;
  }
}

function persistRememberedLogin(enabled: boolean, username: string, password: string) {
  if (!enabled) {
    window.localStorage.removeItem(REMEMBER_LOGIN_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(
    REMEMBER_LOGIN_STORAGE_KEY,
    encodeBase64(
      JSON.stringify({
        username,
        password,
      }),
    ),
  );
}

function normalizePermissions(raw: unknown, fallback: UserPermissions): UserPermissions {
  const source = typeof raw === "object" && raw !== null ? (raw as Record<string, unknown>) : {};
  return {
    targets_read: Boolean(source.targets_read ?? fallback.targets_read),
    targets_create: Boolean(source.targets_create ?? fallback.targets_create),
    targets_update: Boolean(source.targets_update ?? fallback.targets_update),
    targets_delete: Boolean(source.targets_delete ?? fallback.targets_delete),
    webhook_manage: Boolean(source.webhook_manage ?? fallback.webhook_manage),
    poll_manage: Boolean(source.poll_manage ?? fallback.poll_manage),
    proxy_manage: Boolean(source.proxy_manage ?? fallback.proxy_manage),
  };
}

function parseActivityIdFromInput(input: string) {
  const raw = String(input || "").trim();
  if (!raw) {
    return "";
  }

  const extractedUrl = raw.match(/https?:\/\/[^\s]+/i)?.[0] ?? raw;
  try {
    const parsed = new URL(extractedUrl);
    for (const key of ["activityid", "activityId"]) {
      const value = parsed.searchParams.get(key)?.trim();
      if (value) {
        return value;
      }
    }
  } catch {
    // Fall through to regex extraction for pasted text or incomplete URL-like content.
  }

  const matched = raw.match(/[?&](activityid|activityId)=([^&#\s]+)/);
  return matched?.[2]?.trim() ?? "";
}

function createTargetForm(groupKeys: string[] = [], enabled = true): TargetForm {
  return { name: "", url: "", group_keys: groupKeys, enabled };
}

function normalizeTargetGroupKeys(target: Pick<TargetItem, "group_keys" | "group_key">) {
  if (Array.isArray(target.group_keys) && target.group_keys.length) {
    return target.group_keys;
  }
  return target.group_key ? [target.group_key] : [];
}

function toggleTargetGroup(groupKeys: string[], groupKey: string, checked: boolean) {
  if (checked) {
    return groupKeys.includes(groupKey) ? groupKeys : [...groupKeys, groupKey];
  }
  return groupKeys.filter((value) => value !== groupKey);
}

function createGroupForm(): GroupForm {
  return {
    name: "",
    key: "",
    webhook: "",
    clear_webhook: false,
    make_default: false,
  };
}

function createProxyForm(proxy?: ProxyConfig): ProxyForm {
  return {
    enabled: Boolean(proxy?.enabled),
    provider: proxy?.provider || "generic_json",
    request_method: proxy?.request_method || "GET",
    api_url: proxy?.api_url || "",
    api_key: "",
    api_key_header: proxy?.api_key_header || "X-API-Key",
    extra_headers_json: JSON.stringify(proxy?.extra_headers || {}, null, 2),
    query_params_json: JSON.stringify(proxy?.query_params || {}, null, 2),
    request_body_json: JSON.stringify(proxy?.request_body || {}, null, 2),
    response_data_path: proxy?.response_data_path || "",
    response_fields_json: JSON.stringify(
      proxy?.response_fields || DEFAULT_RESPONSE_FIELDS,
      null,
      2,
    ),
    cache_seconds: proxy?.cache_seconds || 120,
    timeout_seconds: proxy?.timeout_seconds || 8,
    sticky_mode: proxy?.sticky_mode || "shared",
    verify_ssl: proxy?.verify_ssl !== false,
  };
}

function stateBadgeVariant(state: string) {
  if (state === "IN_STOCK") {
    return "success" as const;
  }
  if (state === "SOLD_OUT") {
    return "warning" as const;
  }
  return "default" as const;
}

function stateLabel(state: string) {
  if (state === "IN_STOCK") {
    return "有货";
  }
  if (state === "SOLD_OUT") {
    return "售罄";
  }
  return "未知";
}

function parseJsonField(label: string, text: string) {
  try {
    const parsed = JSON.parse(text || "{}") as unknown;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new Error(`${label} 必须是 JSON 对象`);
    }
    return parsed;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`${label} JSON 不合法：${message}`);
  }
}

type LoginFailure = {
  noticeMessage: string;
  inlineMessage: string;
  field?: "password";
};

function resolveLoginFailure(error: unknown): LoginFailure {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) {
      return {
        noticeMessage: "账号或密码错误，请重新输入后再试",
        inlineMessage: "账号或密码错误，请检查后重试。",
        field: "password",
      };
    }
    if (error.code === "network_error") {
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        return {
          noticeMessage: "网络连接失败，请检查本地网络后重试",
          inlineMessage: "网络连接失败，请确认网络可用后再试。",
        };
      }
      return {
        noticeMessage: "服务不可达，请检查网络或稍后重试",
        inlineMessage: "当前无法连接服务，请检查网络后重试。",
      };
    }
    if (typeof error.status === "number" && error.status >= 500) {
      return {
        noticeMessage: "服务不可达，请稍后重试",
        inlineMessage: "服务暂时不可用，请稍后重试。",
      };
    }
    return {
      noticeMessage: error.message || "登录失败，请稍后重试",
      inlineMessage: error.message || "登录失败，请稍后重试。",
    };
  }
  return {
    noticeMessage: error instanceof Error ? error.message : "登录失败，请稍后重试",
    inlineMessage: "登录失败，请稍后重试。",
  };
}

function DataField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-3">
      <Label className="leading-5">{label}</Label>
      {children}
      {hint ? <p className="text-xs leading-5 text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export default function App() {
  const apiBaseUrl = getDefaultBaseUrl();
  const rememberedLogin = useMemo(() => readRememberedLogin(), []);
  const [authToken, setAuthToken] = useState(() =>
    getLocalValue(API_TOKEN_STORAGE_KEY, ""),
  );
  const [dashboard, setDashboard] = useState<Dashboard>(defaultDashboard);
  const [dashboardReady, setDashboardReady] = useState(false);
  const [notice, setNotice] = useState<Notice>({ type: "success", message: "" });
  const [loading, setLoading] = useState<LoadingState>({
    dashboard: false,
    loginSubmit: false,
    targetSubmit: false,
    groupSubmit: false,
    pollSubmit: false,
    proxySubmit: false,
  });
  const [editingGroupKey, setEditingGroupKey] = useState("");
  const [pollSeconds, setPollSeconds] = useState(60);
  const [activeTab, setActiveTab] = useState<TabId>("targets");
  const [showAddTargetModal, setShowAddTargetModal] = useState(false);
  const [editingTarget, setEditingTarget] = useState<TargetItem | null>(null);
  const [targetForm, setTargetForm] = useState<TargetForm>(() => createTargetForm());
  const [targetFormError, setTargetFormError] = useState("");
  const [groupForm, setGroupForm] = useState<GroupForm>(createGroupForm);
  const [proxyForm, setProxyForm] = useState<ProxyForm>(createProxyForm);
  const [users, setUsers] = useState<UserItem[]>([]);
  const [me, setMe] = useState<AuthMeResponse | null>(null);
  const [loginRemember, setLoginRemember] = useState(Boolean(rememberedLogin));
  const [loginUsername, setLoginUsername] = useState(() => rememberedLogin?.username ?? "");
  const [loginPassword, setLoginPassword] = useState(() => rememberedLogin?.password ?? "");
  const [loginFormError, setLoginFormError] = useState("");
  const [loginUsernameError, setLoginUsernameError] = useState("");
  const [loginPasswordError, setLoginPasswordError] = useState("");
  const [permissionUserId, setPermissionUserId] = useState("");
  const [newUserName, setNewUserName] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");

  const isLoggedIn = Boolean(authToken.trim() && me);
  const currentUser = useMemo<AuthUser | null>(() => me?.user ?? null, [me]);

  const currentPermissions = useMemo<UserPermissions>(() => {
    if (!me) {
      return { ...DEFAULT_OPERATOR_PERMISSIONS };
    }
    return normalizePermissions(me.permissions, DEFAULT_OPERATOR_PERMISSIONS);
  }, [me]);

  const selectedPermissionUser = useMemo(
    () => users.find((user) => String(user.id) === permissionUserId) ?? users[0],
    [users, permissionUserId],
  );

  const canManagePermissions = Boolean(currentUser?.is_admin);
  const canTargetsRead = currentPermissions.targets_read;
  const canTargetsCreate = currentPermissions.targets_create;
  const canTargetsUpdate = currentPermissions.targets_update;
  const canTargetsDelete = currentPermissions.targets_delete;
  const canWebhookManage = currentPermissions.webhook_manage;
  const canPollManage = currentPermissions.poll_manage;
  const canProxyManage = currentPermissions.proxy_manage;

  useEffect(() => {
    if (authToken.trim()) {
      void bootstrapSession(false);
      return;
    }
    setMe(null);
    setDashboardReady(false);
  }, [authToken, apiBaseUrl]);

  useEffect(() => {
    if (canManagePermissions && isLoggedIn) {
      void loadUsers();
    }
  }, [canManagePermissions, isLoggedIn]);

  useEffect(() => {
    if (!users.length) {
      setPermissionUserId("");
      return;
    }
    if (!users.find((item) => String(item.id) === permissionUserId)) {
      setPermissionUserId(String(users[0].id));
    }
  }, [users, permissionUserId]);

  useEffect(() => {
    if (!notice.message) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setNotice((current) => ({ ...current, message: "" }));
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [notice.message]);

  useEffect(() => {
    document.title = "饭查查";
  }, []);

  const summaryCards = useMemo(
    () => [
      {
        label: "监控套餐",
        value: dashboard.summary.total_targets,
        hint: "当前配置中的库存目标数量",
        icon: Boxes,
      },
      {
        label: "有货状态",
        value: dashboard.summary.in_stock,
        hint: "最近一次轮询判定为有货",
        icon: Activity,
      },
      {
        label: "售罄状态",
        value: dashboard.summary.sold_out,
        hint: "最近一次轮询判定为售罄",
        icon: CircleAlert,
      },
      {
        label: "异常目标",
        value: dashboard.summary.error_targets,
        hint: "最近一次包含错误信息",
        icon: ShieldCheck,
      },
    ],
    [dashboard.summary],
  );

  async function request<T>(path: string, options?: RequestInit) {
    return (await apiRequest(apiBaseUrl, authToken, path, options)) as T;
  }

  function pushNotice(type: NoticeType, message: string) {
    setNotice({ type, message });
  }

  function hasNavAccess(permission?: NavPermission) {
    if (!permission) {
      return true;
    }
    if (permission === "admin_only") {
      return canManagePermissions;
    }
    return Boolean(currentPermissions[permission]);
  }

  function checkPermission(permission: PermissionKey) {
    if (currentPermissions[permission]) {
      return true;
    }
    pushNotice("error", `当前账号无权限：${PERMISSION_LABELS[permission]}`);
    return false;
  }

  async function loadMe() {
    const payload = await request<AuthMeResponse>("/api/auth/me");
    setMe(payload);
    return payload;
  }

  async function bootstrapSession(withNotice: boolean) {
    try {
      const payload = await loadMe();
      await loadDashboard(false);
      if (withNotice) {
        pushNotice("success", `已登录：${payload.user.username}`);
      }
    } catch (error) {
      setMe(null);
      setDashboardReady(false);
      setUsers([]);
      const message = error instanceof Error ? error.message : "认证失效";
      pushNotice("error", message);
      setAuthToken("");
      window.localStorage.removeItem(API_TOKEN_STORAGE_KEY);
    }
  }

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading.loginSubmit) {
      return;
    }
    const username = loginUsername.trim();
    const missingUsername = !username;
    const missingPassword = !loginPassword;
    if (missingUsername || missingPassword) {
      setLoginFormError("请先完整填写账号和密码。");
      setLoginUsernameError(missingUsername ? "请输入账号" : "");
      setLoginPasswordError(missingPassword ? "请输入密码" : "");
      pushNotice("error", "请先完整填写账号和密码");
      return;
    }
    setLoginFormError("");
    setLoginUsernameError("");
    setLoginPasswordError("");
    setLoading((current) => ({ ...current, loginSubmit: true }));
    try {
      const payload = (await apiRequest(apiBaseUrl, "", "/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username,
          password: loginPassword,
        }),
      })) as { token: string; user: AuthUser; permissions: UserPermissions };
      setAuthToken(payload.token || "");
      setMe({ user: payload.user, permissions: payload.permissions });
      window.localStorage.setItem(API_TOKEN_STORAGE_KEY, payload.token || "");
      persistRememberedLogin(loginRemember, username, loginPassword);
      if (!loginRemember) {
        setLoginPassword("");
      }
      setLoginFormError("");
      setLoginUsernameError("");
      setLoginPasswordError("");
      pushNotice("success", `已登录：${payload.user.username}`);
    } catch (error) {
      const failure = resolveLoginFailure(error);
      setLoginFormError(failure.inlineMessage);
      setLoginUsernameError("");
      setLoginPasswordError(failure.field === "password" ? failure.inlineMessage : "");
      pushNotice("error", failure.noticeMessage);
    } finally {
      setLoading((current) => ({ ...current, loginSubmit: false }));
    }
  }

  function resetSessionState() {
    setAuthToken("");
    setMe(null);
    setUsers([]);
    setDashboard(defaultDashboard());
    setDashboardReady(false);
    setActiveTab("targets");
    setShowAddTargetModal(false);
    setEditingTarget(null);
    window.localStorage.removeItem(API_TOKEN_STORAGE_KEY);
  }

  function handleLogout() {
    const logoutToken = authToken.trim();

    resetSessionState();
    pushNotice("success", "已退出登录");

    if (!logoutToken) {
      return;
    }

    void apiRequest(apiBaseUrl, logoutToken, "/api/auth/logout", { method: "POST" }).catch((error) => {
      pushNotice("error", error instanceof Error ? error.message : "退出登录请求失败");
    });
  }

  async function loadUsers(force = false) {
    if (!force && !canManagePermissions) {
      return;
    }
    try {
      const payload = (await request<{ items: UserItem[] }>("/api/users")) as { items: UserItem[] };
      setUsers(payload.items || []);
    } catch (error) {
      pushNotice("error", error instanceof Error ? error.message : "加载用户失败");
    }
  }

  async function updateUserPermission(user: UserItem, key: PermissionKey, enabled: boolean) {
    if (user.is_admin) {
      return;
    }
    const nextPermissions = {
      ...normalizePermissions(user.permissions, DEFAULT_OPERATOR_PERMISSIONS),
      [key]: enabled,
    };
    try {
      await request(`/api/users/${user.id}/permissions`, {
        method: "PATCH",
        body: JSON.stringify({ permissions: nextPermissions }),
      });
        await loadUsers(true);
      await bootstrapSession(false);
      pushNotice("success", "权限已更新");
    } catch (error) {
      pushNotice("error", error instanceof Error ? error.message : "更新权限失败");
    }
  }

  async function addUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canManagePermissions) {
      pushNotice("error", "仅管理员可新增用户");
      return;
    }
    const username = newUserName.trim();
    if (!username) {
      pushNotice("error", "请先输入用户名");
      return;
    }
    try {
      const payload = (await request<{
        action: string;
        user: UserItem;
        generated_password?: string;
      }>("/api/users", {
        method: "POST",
        body: JSON.stringify({
          username,
          password: newUserPassword || undefined,
          is_admin: false,
        }),
      })) as { generated_password?: string };
      await loadUsers();
      setNewUserName("");
      setNewUserPassword("");
      if (payload.generated_password) {
        pushNotice("success", `用户已创建，系统密码：${payload.generated_password}`);
      } else {
        pushNotice("success", "用户已创建");
      }
    } catch (error) {
      pushNotice("error", error instanceof Error ? error.message : "创建用户失败");
    }
  }

  async function removeUser(user: UserItem) {
    if (!canManagePermissions) {
      pushNotice("error", "仅管理员可删除用户");
      return;
    }
    if (!window.confirm(`删除用户「${user.username}」？`)) {
      return;
    }
    try {
      await request(`/api/users/${user.id}`, { method: "DELETE" });
      await loadUsers();
      pushNotice("success", `已删除用户：${user.username}`);
    } catch (error) {
      pushNotice("error", error instanceof Error ? error.message : "删除用户失败");
    }
  }

  function applyDashboard(payload: Dashboard) {
    setDashboard((current) => ({
      ...payload,
      targets: mergeTargets(current.targets, payload.targets),
    }));
    setDashboardReady(true);
    setPollSeconds(payload.poll.interval_seconds || 60);
    setTargetForm((current) => {
      if (current.group_keys.length || !payload.notify_groups.length) {
        return current;
      }
      return { ...current, group_keys: [payload.notify_groups[0].key] };
    });
    setProxyForm(createProxyForm(payload.proxy));
  }

  async function loadDashboard(withNotice = true) {
    setLoading((current) => ({ ...current, dashboard: true }));
    try {
      const payload = await request<Dashboard>("/api/dashboard");
      applyDashboard(payload);
      if (withNotice) {
        pushNotice("success", "面板已刷新");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "加载面板失败";
      setDashboardReady(false);
      pushNotice("error", message);
    } finally {
      setLoading((current) => ({ ...current, dashboard: false }));
    }
  }

  function openAddTargetModal() {
    if (!checkPermission("targets_create")) {
      return;
    }
    setEditingTarget(null);
    setTargetForm(createTargetForm(dashboard.notify_groups[0]?.key ? [dashboard.notify_groups[0].key] : []));
    setTargetFormError("");
    setShowAddTargetModal(true);
  }

  function openEditTargetModal(target: TargetItem) {
    if (!checkPermission("targets_update")) {
      return;
    }
    setEditingTarget(target);
    setTargetForm({
      name: target.name,
      url: target.url,
      group_keys: normalizeTargetGroupKeys(target),
      enabled: target.enabled,
    });
    setTargetFormError("");
    setShowAddTargetModal(true);
  }

  function submitTarget(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!parseActivityIdFromInput(targetForm.url)) {
      setTargetFormError("链接无效：未识别 activity_id，请检查链接或手动填写 activity_id");
      return;
    }
    if (dashboard.notify_groups.length > 0 && targetForm.group_keys.length === 0) {
      setTargetFormError("请至少选择一个通知分组");
      return;
    }

    const permission = editingTarget ? "targets_update" : "targets_create";
    const editingTargetSnapshot = editingTarget;
    const targetFormSnapshot = { ...targetForm, group_keys: [...targetForm.group_keys] };
    const defaultGroupKeys = dashboard.notify_groups[0]?.key ? [dashboard.notify_groups[0].key] : [];

    setTargetFormError("");
    setShowAddTargetModal(false);
    setEditingTarget(null);
    setTargetForm(createTargetForm(defaultGroupKeys));

    if (!checkPermission(permission)) {
      return;
    }

    void (async () => {
      try {
        if (editingTargetSnapshot) {
          await request(`/api/targets/${editingTargetSnapshot.index}`, {
            method: "PATCH",
            body: JSON.stringify({
              set_name: targetFormSnapshot.name,
              set_url: targetFormSnapshot.url,
              set_group_keys: targetFormSnapshot.group_keys,
              set_enabled: targetFormSnapshot.enabled,
            }),
          });
          pushNotice("success", `已更新套餐 #${editingTargetSnapshot.index}`);
        } else {
          await request("/api/targets", {
            method: "POST",
            body: JSON.stringify(targetFormSnapshot),
          });
          pushNotice("success", "已新增套餐");
        }
        await loadDashboard(false);
      } catch (error) {
        pushNotice("error", error instanceof Error ? error.message : "提交套餐失败");
      }
    })();
  }

  async function removeTarget(target: TargetItem) {
    if (!checkPermission("targets_delete")) {
      return;
    }
    if (!window.confirm(`删除监控套餐「${target.name}」？`)) {
      return;
    }
    try {
      await request(`/api/targets/${target.index}`, { method: "DELETE" });
      pushNotice("success", `已删除套餐 #${target.index}`);
      await loadDashboard();
    } catch (error) {
      pushNotice("error", error instanceof Error ? error.message : "删除套餐失败");
    }
  }

  async function toggleTargetEnabled(target: TargetItem, enabled: boolean) {
    if (!checkPermission("targets_update")) {
      return;
    }
    try {
      await request(`/api/targets/${target.index}`, {
        method: "PATCH",
        body: JSON.stringify({
          set_enabled: enabled,
        }),
      });
      pushNotice("success", enabled ? `已启用套餐 #${target.index}` : `已停用套餐 #${target.index}`);
      await loadDashboard(false);
    } catch (error) {
      pushNotice("error", error instanceof Error ? error.message : "更新启停状态失败");
    }
  }

  function resetGroupForm() {
    setEditingGroupKey("");
    setGroupForm(createGroupForm());
  }

  function startEditGroup(group: NotifyGroup) {
    if (!checkPermission("webhook_manage")) {
      return;
    }
    setActiveTab("groups");
    setEditingGroupKey(group.key);
    setGroupForm({
      name: group.name,
      key: group.key,
      webhook: "",
      clear_webhook: false,
      make_default: Boolean(group.is_default),
    });
  }

  async function submitGroup(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!checkPermission("webhook_manage")) {
      return;
    }
    setLoading((current) => ({ ...current, groupSubmit: true }));
    try {
      if (editingGroupKey) {
        const payload: Record<string, unknown> = {
          set_name: groupForm.name,
          make_default: groupForm.make_default,
        };
        if (groupForm.webhook) {
          payload.set_webhook = groupForm.webhook;
        } else if (groupForm.clear_webhook) {
          payload.set_webhook = "";
        }
        await request(`/api/notify-groups/${encodeURIComponent(editingGroupKey)}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        pushNotice("success", `已更新分组 ${editingGroupKey}`);
      } else {
        await request("/api/notify-groups", {
          method: "POST",
          body: JSON.stringify({
            name: groupForm.name,
            key: groupForm.key,
            webhook: groupForm.webhook,
          }),
        });
        pushNotice("success", "已新增分组");
      }
      resetGroupForm();
      await loadDashboard();
    } catch (error) {
      pushNotice("error", error instanceof Error ? error.message : "保存分组失败");
    } finally {
      setLoading((current) => ({ ...current, groupSubmit: false }));
    }
  }

  async function removeGroup(group: NotifyGroup) {
    if (!checkPermission("webhook_manage")) {
      return;
    }
    if (!window.confirm(`删除推送分组「${group.name}」？`)) {
      return;
    }
    try {
      await request(`/api/notify-groups/${encodeURIComponent(group.key)}`, {
        method: "DELETE",
      });
      if (editingGroupKey === group.key) {
        resetGroupForm();
      }
      pushNotice("success", `已删除分组 ${group.key}`);
      await loadDashboard();
    } catch (error) {
      pushNotice("error", error instanceof Error ? error.message : "删除分组失败");
    }
  }

  async function submitPoll(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!checkPermission("poll_manage")) {
      return;
    }
    setLoading((current) => ({ ...current, pollSubmit: true }));
    try {
      await request("/api/poll", {
        method: "PUT",
        body: JSON.stringify({ seconds: pollSeconds }),
      });
      pushNotice("success", "轮询频率已更新");
      await loadDashboard();
    } catch (error) {
      pushNotice("error", error instanceof Error ? error.message : "更新轮询频率失败");
    } finally {
      setLoading((current) => ({ ...current, pollSubmit: false }));
    }
  }

  async function submitProxy(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!checkPermission("proxy_manage")) {
      return;
    }
    setLoading((current) => ({ ...current, proxySubmit: true }));
    try {
      const payload = {
        enabled: proxyForm.enabled,
        provider: proxyForm.provider,
        request_method: proxyForm.request_method,
        api_url: proxyForm.api_url,
        api_key: proxyForm.api_key,
        api_key_header: proxyForm.api_key_header,
        extra_headers: parseJsonField("extra_headers", proxyForm.extra_headers_json),
        query_params: parseJsonField("query_params", proxyForm.query_params_json),
        request_body: parseJsonField("request_body", proxyForm.request_body_json),
        response_data_path: proxyForm.response_data_path,
        response_fields: parseJsonField("response_fields", proxyForm.response_fields_json),
        cache_seconds: proxyForm.cache_seconds,
        timeout_seconds: proxyForm.timeout_seconds,
        sticky_mode: proxyForm.sticky_mode,
        verify_ssl: proxyForm.verify_ssl,
      };
      await request("/api/proxy", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      pushNotice("success", "代理配置已更新");
      await loadDashboard();
    } catch (error) {
      pushNotice("error", error instanceof Error ? error.message : "保存代理配置失败");
    } finally {
      setLoading((current) => ({ ...current, proxySubmit: false }));
    }
  }

  const navItems = NAV_ITEMS;
  const visibleNavItems = useMemo(
    () => navItems.filter((item) => hasNavAccess(item.permission)),
    [navItems, canManagePermissions, currentPermissions],
  );

  const activeNavItem =
    visibleNavItems.find((item) => item.id === activeTab) ?? visibleNavItems[0] ?? NAV_ITEMS[0];

  useEffect(() => {
    if (visibleNavItems.find((item) => item.id === activeTab)) {
      return;
    }
    const fallback = visibleNavItems[0]?.id ?? "connection";
    setActiveTab(fallback);
  }, [activeTab, visibleNavItems]);

  if (!isLoggedIn) {
    return (
      <div className="app-shell glass-grid relative min-h-screen overflow-x-hidden">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(circle_at_top_right,rgba(244,115,74,0.22),transparent_45%)]" />
        <div className="pointer-events-none absolute bottom-0 left-0 h-72 w-72 rounded-full bg-[radial-gradient(circle,rgba(83,168,153,0.24),transparent_65%)] blur-3xl" />
        <GlobalNoticeToast notice={notice} />
        <main className="container relative z-10 py-8 sm:py-10">
          <div className="mx-auto max-w-lg">
            <Card className="border-white/65 bg-white/88">
              <CardHeader>
                <CardTitle>登录饭查查</CardTitle>
                <CardDescription>使用你的账号登录饭查查，最长60天登录有效。</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <form className="space-y-4" onSubmit={handleLogin}>
                  <DataField label="用户名">
                    <Input
                      value={loginUsername}
                      placeholder="请输入用户名"
                      className={loginUsernameError ? "border-rose-300 focus-visible:border-rose-400" : ""}
                      onChange={(event) => {
                        setLoginUsername(event.target.value);
                        setLoginUsernameError("");
                        setLoginFormError("");
                      }}
                    />
                    {loginUsernameError ? (
                      <p className="text-xs text-rose-600">{loginUsernameError}</p>
                    ) : null}
                  </DataField>
                  <DataField label="密码">
                    <Input
                      type="password"
                      value={loginPassword}
                      placeholder="请输入密码"
                      className={loginPasswordError ? "border-rose-300 focus-visible:border-rose-400" : ""}
                      onChange={(event) => {
                        setLoginPassword(event.target.value);
                        setLoginPasswordError("");
                        setLoginFormError("");
                      }}
                    />
                    {loginPasswordError ? (
                      <p className="text-xs text-rose-600">{loginPasswordError}</p>
                    ) : null}
                  </DataField>
                  <label className="flex items-start gap-3 rounded-xl border border-border/60 bg-secondary/25 px-3 py-3 text-sm">
                    <input
                      type="checkbox"
                      checked={loginRemember}
                      className="mt-1 h-4 w-4 rounded border-input text-primary"
                      onChange={(event) => {
                        const checked = event.target.checked;
                        setLoginRemember(checked);
                        if (!checked) {
                          persistRememberedLogin(false, "", "");
                        }
                      }}
                    />
                    <span className="space-y-1">
                      <span className="block font-medium text-foreground">记住账号密码</span>
                      <span className="block text-xs leading-5 text-muted-foreground">
                        仅保存在当前设备，请勿在公用设备勾选。
                      </span>
                    </span>
                  </label>
                  {loginFormError ? (
                    <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                      {loginFormError}
                    </div>
                  ) : null}
                  <div className="flex gap-2">
                    <Button type="submit" disabled={loading.loginSubmit}>
                      {loading.loginSubmit ? "登录中..." : "登录"}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell glass-grid relative min-h-screen overflow-x-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(circle_at_top_right,rgba(244,115,74,0.22),transparent_45%)]" />
      <div className="pointer-events-none absolute bottom-0 left-0 h-72 w-72 rounded-full bg-[radial-gradient(circle,rgba(83,168,153,0.24),transparent_65%)] blur-3xl" />
      <GlobalNoticeToast notice={notice} />

      <main className="container relative z-10 py-4 sm:py-6 lg:py-8">
        <section className="min-w-0 space-y-5 pb-8">
          <Card className="border-white/65 bg-white/88">
            <CardContent className="flex min-w-0 flex-col gap-4 p-4 sm:p-5 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0 space-y-3">
                <div className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-secondary/70 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  <Cable className="h-3.5 w-3.5" />
                  饭查查管理台
                </div>
                <div className="min-w-0 space-y-1">
                  <CardTitle>饭查查后台</CardTitle>
                  <CardDescription>账号操作位于顶部，功能切换与内容区分层展示。</CardDescription>
                </div>
              </div>
              <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
                <div className="flex min-w-0 items-center gap-2">
                  <Badge variant="accent" className="max-w-full truncate">
                    {currentUser?.username || "未知用户"}
                  </Badge>
                  <span className="text-sm text-muted-foreground">当前账号</span>
                </div>
                <Button
                  variant="outline"
                  onClick={handleLogout}
                  size="sm"
                  className="w-full sm:w-auto"
                >
                  <LogOut className="h-4 w-4" />
                  退出登录
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/65 bg-white/82">
            <CardContent className="space-y-3 p-4 sm:p-5">
              <div className="text-sm font-medium">功能切换</div>
              <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 lg:flex-wrap lg:overflow-visible">
                {visibleNavItems.map((item) => {
                  const Icon = item.icon;
                  const active = item.id === activeTab;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      title={item.hint}
                      onClick={() => setActiveTab(item.id)}
                      className={cn(
                        "inline-flex min-h-10 shrink-0 items-center gap-2 rounded-xl border px-3.5 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25 lg:flex-1",
                        active
                          ? "border-primary/35 bg-primary/10 text-foreground"
                          : "border-border/70 bg-background text-muted-foreground hover:border-border hover:bg-secondary/40",
                      )}
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      <span className="truncate">{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/65 bg-white/72">
            <CardContent className="flex min-w-0 flex-col gap-4 p-4 sm:p-5 lg:flex-row lg:items-center lg:justify-between">
              <div className="space-y-1">
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                  {activeNavItem.label}
                </p>
                <p className="text-sm text-muted-foreground">{activeNavItem.hint}</p>
              </div>
            </CardContent>
          </Card>

          {activeTab === "connection" ? (
            <section className="grid gap-5">
              <section className="grid gap-5 rounded-[2rem] border border-white/60 bg-hero p-5 shadow-panel sm:p-6">
                  <div className="space-y-4">
                    <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">连接设置</h1>
                    <p className="text-sm leading-7 text-muted-foreground">
                      在这里查看连接状态与鉴权状态。
                    </p>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {summaryCards.map((card) => {
                        const Icon = card.icon;
                        return (
                          <Card key={card.label} className="bg-white/78">
                            <CardContent className="flex items-start justify-between p-5">
                              <div>
                                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                                  {card.label}
                                </p>
                                <p className="mt-3 text-3xl font-bold">{card.value}</p>
                                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                                  {card.hint}
                                </p>
                              </div>
                              <div className="rounded-2xl bg-secondary p-3 text-primary">
                                <Icon className="h-5 w-5" />
                              </div>
                            </CardContent>
                          </Card>
                        );
                      })}
                    </div>
                  </div>
              </section>
            </section>
          ) : null}

          {activeTab === "targets" ? (
            <Card>
                <CardHeader className="pb-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="space-y-2">
                      <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                        套餐管理
                      </div>
                      <CardTitle>监控套餐</CardTitle>
                      <CardDescription>
                        统一管理需要关注的套餐，支持快速新增、编辑与删除。
                      </CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void loadDashboard()}
                        disabled={!canTargetsRead}
                        title={canTargetsRead ? "刷新目标列表" : "当前账号无查看监控列表权限"}
                      >
                        刷新列表
                      </Button>
                      <Button
                        size="sm"
                        onClick={openAddTargetModal}
                        disabled={!canTargetsCreate}
                        title={canTargetsCreate ? "新增监控项" : "当前账号无新增监控项权限"}
                      >
                        <Plus className="h-4 w-4" />
                        新增监控
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-5">
                  {!canTargetsRead ? (
                    <div className="rounded-[1.35rem] border border-dashed border-border bg-secondary/30 p-5 text-sm text-muted-foreground">
                      当前账号没有查看监控列表的权限。
                    </div>
                  ) : (
                    <div className="grid gap-3">
                    {loading.dashboard || !dashboardReady ? (
                      <div className="rounded-[1.35rem] border border-dashed border-border bg-secondary/30 p-5 text-sm text-muted-foreground">
                        加载中...
                      </div>
                    ) : dashboard.targets.length ? (
                      dashboard.targets.map((target) => (
                        <div
                          key={`${target.activity_id}-${target.index}`}
                          className="rounded-[1.35rem] border border-border/70 bg-secondary/40 p-5"
                        >
                          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                            <div className="space-y-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <Badge variant="accent">#{target.index}</Badge>
                                <h3 className="text-base font-semibold">{target.name}</h3>
                                <Badge variant={stateBadgeVariant(target.last_state)}>
                                  {stateLabel(target.last_state)}
                                </Badge>
                              </div>
                              <div className="flex flex-wrap gap-2 pt-1">
                                {normalizeTargetGroupKeys(target).map((groupKey, index) => (
                                  <Badge key={`${target.activity_id}-${groupKey}`} variant="default">
                                    {(target.group_names?.[index] || target.group_name || groupKey)} / {groupKey}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                              <label className="flex items-center gap-2 rounded-xl border border-border/60 bg-white/70 px-3 py-2 text-sm">
                                <span className="text-muted-foreground">启用</span>
                                <Switch
                                  checked={target.enabled}
                                  disabled={!canTargetsUpdate}
                                  onCheckedChange={(checked) => void toggleTargetEnabled(target, checked)}
                                />
                              </label>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => openEditTargetModal(target)}
                                disabled={!canTargetsUpdate}
                                title={canTargetsUpdate ? "编辑监控项" : "当前账号无编辑监控项权限"}
                              >
                                编辑
                              </Button>
                              <Button
                                type="button"
                                variant="destructive"
                                size="sm"
                                disabled={!canTargetsDelete}
                                title={canTargetsDelete ? "删除监控项" : "当前账号无删除监控项权限"}
                                onClick={() => void removeTarget(target)}
                              >
                                删除
                              </Button>
                            </div>
                          </div>
                          {target.last_title ? (
                            <p className="mt-3 text-sm text-muted-foreground">
                              页面标题：{target.last_title}
                            </p>
                          ) : null}
                          <a
                            className="mt-3 block break-all text-sm"
                            href={target.url}
                            rel="noreferrer"
                            target="_blank"
                          >
                            {target.url}
                          </a>
                          <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                            <span>最近变更：{target.last_change_ts || "暂无"}</span>
                            <span>失败次数：{target.fail_count || 0}</span>
                            <span>错误连击：{target.last_error_streak || 0}</span>
                          </div>
                          <div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                            <span>启用状态：{target.enabled ? "启用中" : "已停用"}</span>
                            <span>自动停查计数：{target.consecutive_null_brief_count || 0}</span>
                            <span>停查原因：{target.disabled_reason || "无"}</span>
                          </div>
                          {target.last_error_text ? (
                            <p className="mt-3 rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-700">
                              {target.last_error_text}
                            </p>
                          ) : null}
                        </div>
                      ))
                    ) : (
                      <div className="rounded-[1.35rem] border border-dashed border-border bg-secondary/30 p-5 text-sm text-muted-foreground">
                        还没有监控套餐，点击右上角“新增监控”开始配置。
                      </div>
                    )}
                    </div>
                  )}
                </CardContent>
            </Card>
          ) : null}

            {activeTab === "groups" ? (
              <Card>
                <CardHeader className="pb-4">
                  <div className="space-y-2">
                    <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                      通知管理
                    </div>
                    <CardTitle>通知分组</CardTitle>
                    <CardDescription>管理通知分组与通知地址的对应关系。</CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="space-y-5">
                  {!canWebhookManage ? (
                    <div className="rounded-[1.35rem] border border-dashed border-border bg-secondary/30 p-5 text-sm text-muted-foreground">
                      当前账号没有管理通知分组的权限，当前页面为只读状态。
                    </div>
                  ) : null}
                  <form className="grid gap-4" onSubmit={submitGroup}>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <DataField label="分组名">
                        <Input
                          required
                          disabled={!canWebhookManage}
                          value={groupForm.name}
                          placeholder="例如：武汉群"
                          onChange={(event) =>
                            setGroupForm((current) => ({
                              ...current,
                              name: event.target.value,
                            }))
                          }
                        />
                      </DataField>
                      <DataField label="分组标识">
                        <Input
                          value={groupForm.key}
                          disabled={Boolean(editingGroupKey) || !canWebhookManage}
                          placeholder="留空则自动生成"
                          onChange={(event) =>
                            setGroupForm((current) => ({
                              ...current,
                              key: event.target.value,
                            }))
                          }
                        />
                      </DataField>
                    </div>
                    <DataField label="通知地址">
                      <Input
                        disabled={!canWebhookManage}
                        value={groupForm.webhook}
                        placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
                        onChange={(event) =>
                          setGroupForm((current) => ({
                            ...current,
                            webhook: event.target.value,
                          }))
                        }
                      />
                    </DataField>
                    {editingGroupKey ? (
                      <div className="grid gap-3 rounded-[1.25rem] bg-secondary/45 p-4 text-sm">
                        <label className="flex items-center justify-between gap-3">
                          <span>保存时清空该分组的通知地址</span>
                          <Switch
                            disabled={!canWebhookManage}
                            checked={groupForm.clear_webhook}
                            onCheckedChange={(checked) =>
                              setGroupForm((current) => ({
                                ...current,
                                clear_webhook: checked,
                              }))
                            }
                          />
                        </label>
                        <label className="flex items-center justify-between gap-3">
                          <span>设为默认分组</span>
                          <Switch
                            disabled={!canWebhookManage}
                            checked={groupForm.make_default}
                            onCheckedChange={(checked) =>
                              setGroupForm((current) => ({
                                ...current,
                                make_default: checked,
                              }))
                            }
                          />
                        </label>
                      </div>
                    ) : null}
                    <div className="flex flex-wrap gap-3">
                      <Button
                        type="submit"
                        disabled={loading.groupSubmit || !canWebhookManage}
                        title={canWebhookManage ? "保存分组" : "当前账号无管理通知分组权限"}
                      >
                        {loading.groupSubmit
                          ? "提交中..."
                          : editingGroupKey
                            ? "保存分组"
                            : "新增分组"}
                      </Button>
                      {editingGroupKey ? (
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={resetGroupForm}
                          disabled={!canWebhookManage}
                        >
                          取消编辑
                        </Button>
                      ) : null}
                    </div>
                  </form>

                  <div className="grid gap-3">
                    {dashboard.notify_groups.map((group) => (
                      <div
                        key={group.key}
                        className="rounded-[1.35rem] border border-border/70 bg-secondary/40 p-5"
                      >
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                          <div>
                            <h3 className="text-base font-semibold">{group.name}</h3>
                            <p className="mt-1 text-sm text-muted-foreground">{group.key}</p>
                          </div>
                          <Badge variant={group.is_default ? "accent" : "default"}>
                            {group.is_default ? "默认分组" : "备用分组"}
                          </Badge>
                        </div>
                        <p className="mt-3 text-sm text-muted-foreground">
                          通知地址：{group.webhook_masked || "未配置"}
                        </p>
                        <p className="mt-1 text-sm text-muted-foreground">
                          状态：{group.webhook_configured ? "已配置" : "未配置"}
                        </p>
                        <div className="mt-4 flex flex-wrap gap-3">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={!canWebhookManage}
                            title={canWebhookManage ? "编辑分组" : "当前账号无管理通知分组权限"}
                            onClick={() => startEditGroup(group)}
                          >
                            编辑
                          </Button>
                          <Button
                            type="button"
                            variant="destructive"
                            size="sm"
                            disabled={dashboard.notify_groups.length <= 1 || !canWebhookManage}
                            title={
                              canWebhookManage
                                ? "删除分组"
                                : "当前账号无管理通知分组权限"
                            }
                            onClick={() => void removeGroup(group)}
                          >
                            删除
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ) : null}

            {activeTab === "poll" ? (
              <Card>
                <CardHeader>
                  <div className="space-y-2">
                    <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                      刷新节奏
                    </div>
                    <CardTitle>轮询配置</CardTitle>
                    <CardDescription>调整轮询频率，控制刷新节奏。</CardDescription>
                  </div>
                </CardHeader>
                <CardContent>
                  {!canPollManage ? (
                    <div className="mb-4 rounded-xl border border-dashed border-border bg-secondary/30 p-4 text-sm text-muted-foreground">
                      当前账号没有修改刷新频率的权限。
                    </div>
                  ) : null}
                  <form className="grid gap-4" onSubmit={submitPoll}>
                    <DataField label="轮询秒数" hint="后端要求最小值为 5 秒。">
                      <Input
                        min={5}
                        step={1}
                        type="number"
                        disabled={!canPollManage}
                        value={pollSeconds}
                        onChange={(event) => setPollSeconds(Number(event.target.value))}
                      />
                    </DataField>
                    <Button
                      type="submit"
                      disabled={loading.pollSubmit || !canPollManage}
                      title={canPollManage ? "保存轮询配置" : "当前账号无管理轮询配置权限"}
                    >
                      {loading.pollSubmit ? "保存中..." : "保存轮询配置"}
                    </Button>
                  </form>
                </CardContent>
              </Card>
            ) : null}

            {activeTab === "proxy" ? (
              <Card>
                <CardHeader>
                  <div className="space-y-2">
                    <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                      访问保障
                    </div>
                    <CardTitle>代理设置</CardTitle>
                    <CardDescription>管理访问通道参数，保障连接稳定性。</CardDescription>
                  </div>
                </CardHeader>
                <CardContent>
                  {!canProxyManage ? (
                    <div className="mb-4 rounded-xl border border-dashed border-border bg-secondary/30 p-4 text-sm text-muted-foreground">
                      当前账号没有修改访问通道设置的权限。
                    </div>
                  ) : null}
                  <form className="grid gap-4" onSubmit={submitProxy}>
                    <div className="grid gap-4 rounded-[1.4rem] bg-secondary/45 p-4 sm:grid-cols-3">
                      <label className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-white/75 px-4 py-3 sm:col-span-1">
                        <span className="text-sm font-medium">启用访问通道</span>
                        <Switch
                          disabled={!canProxyManage}
                          checked={proxyForm.enabled}
                          onCheckedChange={(checked) =>
                            setProxyForm((current) => ({ ...current, enabled: checked }))
                          }
                        />
                      </label>
                      <DataField label="通道类型">
                        <Input
                          disabled={!canProxyManage}
                          value={proxyForm.provider}
                          placeholder="generic_json"
                          onChange={(event) =>
                            setProxyForm((current) => ({
                              ...current,
                              provider: event.target.value,
                            }))
                          }
                        />
                      </DataField>
                      <DataField label="请求方法">
                        <Select
                          disabled={!canProxyManage}
                          value={proxyForm.request_method}
                          onChange={(event) =>
                            setProxyForm((current) => ({
                              ...current,
                              request_method: event.target.value,
                            }))
                          }
                        >
                          <option value="GET">GET</option>
                          <option value="POST">POST</option>
                        </Select>
                      </DataField>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                      <DataField label="服务地址">
                        <Input
                          disabled={!canProxyManage}
                          value={proxyForm.api_url}
                          placeholder="https://proxy-provider.example.com/get"
                          onChange={(event) =>
                            setProxyForm((current) => ({
                              ...current,
                              api_url: event.target.value,
                            }))
                          }
                        />
                      </DataField>
                      <DataField label="鉴权请求头名称">
                        <Input
                          disabled={!canProxyManage}
                          value={proxyForm.api_key_header}
                          placeholder="X-API-Key"
                          onChange={(event) =>
                            setProxyForm((current) => ({
                              ...current,
                              api_key_header: event.target.value,
                            }))
                          }
                        />
                      </DataField>
                    </div>

                    <DataField label="访问密钥" hint="留空不会清除服务端已保存的访问密钥。">
                      <Input
                        type="password"
                        disabled={!canProxyManage}
                        value={proxyForm.api_key}
                        placeholder={
                          dashboard.proxy.api_key_configured ? "服务端已配置，可按需覆盖" : "保存后写入服务端配置"
                        }
                        onChange={(event) =>
                          setProxyForm((current) => ({
                            ...current,
                            api_key: event.target.value,
                          }))
                        }
                      />
                    </DataField>

                    <div className="grid gap-4 sm:grid-cols-3">
                      <DataField label="缓存秒数">
                        <Input
                          min={1}
                          step={1}
                          type="number"
                          disabled={!canProxyManage}
                          value={proxyForm.cache_seconds}
                          onChange={(event) =>
                            setProxyForm((current) => ({
                              ...current,
                              cache_seconds: Number(event.target.value),
                            }))
                          }
                        />
                      </DataField>
                      <DataField label="超时秒数">
                        <Input
                          min={1}
                          step={1}
                          type="number"
                          disabled={!canProxyManage}
                          value={proxyForm.timeout_seconds}
                          onChange={(event) =>
                            setProxyForm((current) => ({
                              ...current,
                              timeout_seconds: Number(event.target.value),
                            }))
                          }
                        />
                      </DataField>
                      <DataField label="保持方式">
                        <Select
                          disabled={!canProxyManage}
                          value={proxyForm.sticky_mode}
                          onChange={(event) =>
                            setProxyForm((current) => ({
                              ...current,
                              sticky_mode: event.target.value,
                            }))
                          }
                        >
                          <option value="shared">共享</option>
                          <option value="per_target">按套餐独立</option>
                        </Select>
                      </DataField>
                    </div>

                    <label className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-secondary/45 px-4 py-3 text-sm">
                      <span>校验服务地址的 SSL 证书</span>
                      <Switch
                        disabled={!canProxyManage}
                        checked={proxyForm.verify_ssl}
                        onCheckedChange={(checked) =>
                          setProxyForm((current) => ({ ...current, verify_ssl: checked }))
                        }
                      />
                    </label>

                    <div className="grid gap-4 lg:grid-cols-2">
                      <DataField label="额外请求头（JSON）">
                        <Textarea
                          disabled={!canProxyManage}
                          value={proxyForm.extra_headers_json}
                          onChange={(event) =>
                            setProxyForm((current) => ({
                              ...current,
                              extra_headers_json: event.target.value,
                            }))
                          }
                        />
                      </DataField>
                      <DataField label="地址参数（JSON）">
                        <Textarea
                          disabled={!canProxyManage}
                          value={proxyForm.query_params_json}
                          onChange={(event) =>
                            setProxyForm((current) => ({
                              ...current,
                              query_params_json: event.target.value,
                            }))
                          }
                        />
                      </DataField>
                    </div>

                    <div className="grid gap-4 lg:grid-cols-2">
                      <DataField label="请求内容（JSON）">
                        <Textarea
                          disabled={!canProxyManage}
                          value={proxyForm.request_body_json}
                          onChange={(event) =>
                            setProxyForm((current) => ({
                              ...current,
                              request_body_json: event.target.value,
                            }))
                          }
                        />
                      </DataField>
                      <DataField label="返回字段映射（JSON）">
                        <Textarea
                          disabled={!canProxyManage}
                          value={proxyForm.response_fields_json}
                          onChange={(event) =>
                            setProxyForm((current) => ({
                              ...current,
                              response_fields_json: event.target.value,
                            }))
                          }
                        />
                      </DataField>
                    </div>

                    <DataField label="返回数据路径">
                      <Input
                        disabled={!canProxyManage}
                        value={proxyForm.response_data_path}
                        placeholder="例如 data.items.0"
                        onChange={(event) =>
                          setProxyForm((current) => ({
                            ...current,
                            response_data_path: event.target.value,
                          }))
                        }
                      />
                    </DataField>

                    <div className="flex flex-wrap items-center gap-3">
                      <Button
                        type="submit"
                        disabled={loading.proxySubmit || !canProxyManage}
                        title={canProxyManage ? "保存代理配置" : "当前账号无管理代理配置权限"}
                      >
                        {loading.proxySubmit ? "保存中..." : "保存代理配置"}
                      </Button>
                    </div>
                  </form>
                </CardContent>
              </Card>
            ) : null}

            {activeTab === "permissions" ? (
              <Card>
                <CardHeader>
                  <div className="space-y-2">
                    <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                      账号管理
                    </div>
                    <CardTitle>用户功能权限</CardTitle>
                    <CardDescription>管理后台账号及功能访问权限。</CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="space-y-5">
                  {!canManagePermissions ? (
                    <div className="rounded-[1.35rem] border border-dashed border-border bg-secondary/30 p-5 text-sm text-muted-foreground">
                      当前账号不是管理员，无法查看权限配置。
                    </div>
                  ) : (
                    <>
                      <form className="grid gap-3 sm:grid-cols-3" onSubmit={addUser}>
                        <Input
                          value={newUserName}
                          placeholder="新增普通用户，例如：operator01"
                          onChange={(event) => setNewUserName(event.target.value)}
                        />
                        <Input
                          type="password"
                          value={newUserPassword}
                          placeholder="密码（可选，留空自动生成）"
                          onChange={(event) => setNewUserPassword(event.target.value)}
                        />
                        <Button type="submit">新增用户</Button>
                      </form>
                      <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
                        <div className="grid gap-3">
                          {users.map((user) => (
                            <button
                              key={user.id}
                              type="button"
                              onClick={() => setPermissionUserId(String(user.id))}
                              className={cn(
                                "rounded-xl border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25",
                                String(selectedPermissionUser?.id) === String(user.id)
                                  ? "border-primary/35 bg-primary/10"
                                  : "border-border/70 bg-secondary/40 hover:border-border hover:bg-secondary/55",
                              )}
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-medium">{user.username}</span>
                                <Badge variant={user.is_admin ? "accent" : "default"}>
                                  {user.is_admin ? "管理员" : "普通用户"}
                                </Badge>
                              </div>
                              <p className="mt-1 break-all text-xs text-muted-foreground">{user.id}</p>
                            </button>
                          ))}
                        </div>
                        {selectedPermissionUser ? (
                          <div className="space-y-4 rounded-xl border border-border/70 bg-secondary/35 p-5">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div>
                                <p className="text-sm font-semibold">{selectedPermissionUser.username}</p>
                                <p className="text-xs text-muted-foreground">
                                  用户 ID：{selectedPermissionUser.id}
                                </p>
                              </div>
                              <div className="flex items-center gap-2">
                                <Button
                                  type="button"
                                  variant="destructive"
                                  size="sm"
                                  disabled={
                                    selectedPermissionUser.is_admin ||
                                    selectedPermissionUser.id === currentUser?.id
                                  }
                                  onClick={() => void removeUser(selectedPermissionUser)}
                                >
                                  删除用户
                                </Button>
                              </div>
                            </div>
                            <div className="grid gap-3">
                              {PERMISSION_KEYS.map((permission) => (
                                <label
                                  key={permission}
                                  className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-white/70 px-4 py-3 text-sm"
                                >
                                  <div className="space-y-1">
                                    <p className="font-medium text-foreground">
                                      {PERMISSION_LABELS[permission]}
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                      {PERMISSION_DESCRIPTIONS[permission]}
                                    </p>
                                  </div>
                                  <Switch
                                    disabled={selectedPermissionUser.is_admin}
                                    checked={
                                      selectedPermissionUser.is_admin
                                        ? true
                                        : Boolean(selectedPermissionUser.permissions[permission])
                                    }
                                    onCheckedChange={(checked) =>
                                      void updateUserPermission(selectedPermissionUser, permission, checked)
                                    }
                                  />
                                </label>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            ) : null}

            {showAddTargetModal
              ? createPortal(
                  <div
                    className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/35 p-4 sm:items-center"
                    onClick={() => {
                      setShowAddTargetModal(false);
                      setEditingTarget(null);
                      setTargetFormError("");
                    }}
                  >
                <Card
                  className="z-50 my-6 w-full max-w-xl max-h-[90vh] overflow-y-auto"
                  onClick={(event) => event.stopPropagation()}
                >
                  <CardHeader className="pb-3">
                    <CardTitle>{editingTarget ? "编辑监控" : "新增监控"}</CardTitle>
                    <CardDescription>
                      填写名称、链接和通知分组后，提交即可立即生效。
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <form className="grid gap-4" onSubmit={submitTarget}>
                      <DataField label="名字">
                        <Input
                          required
                          value={targetForm.name}
                          placeholder="例如：春意寻味双人餐"
                          onChange={(event) =>
                            setTargetForm((current) => ({
                              ...current,
                              name: event.target.value,
                            }))
                          }
                        />
                      </DataField>
                      <DataField label="链接">
                        <Input
                          required
                          value={targetForm.url}
                          placeholder="https://m.dianping.com/app/femember-groupbuyinter-static/main.html?activityid=..."
                          className={targetFormError ? "border-rose-300 focus-visible:border-rose-400" : ""}
                          onChange={(event) => {
                            setTargetForm((current) => ({
                              ...current,
                              url: event.target.value,
                            }));
                            setTargetFormError("");
                          }}
                        />
                        {targetFormError ? (
                          <p className="text-xs text-rose-600">{targetFormError}</p>
                        ) : null}
                      </DataField>
                      <label className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-secondary/35 px-4 py-3 text-sm">
                        <span>启用该监控</span>
                        <Switch
                          checked={targetForm.enabled}
                          onCheckedChange={(checked) =>
                            setTargetForm((current) => ({
                              ...current,
                              enabled: checked,
                            }))
                          }
                        />
                      </label>
                      <DataField label="通知分组" hint="可多选，至少选择一个分组。">
                        <div className="grid gap-3 rounded-[1.15rem] border border-border/70 bg-secondary/35 p-3">
                          {dashboard.notify_groups.map((group) => {
                            const checked = targetForm.group_keys.includes(group.key);
                            return (
                              <label
                                key={group.key}
                                className={cn(
                                  "flex items-center justify-between gap-3 rounded-xl border px-3 py-2 text-sm transition-colors",
                                  checked
                                    ? "border-primary/40 bg-primary/10"
                                    : "border-border/60 bg-white/70",
                                )}
                              >
                                <div>
                                  <p className="font-medium">{group.name}</p>
                                  <p className="text-xs text-muted-foreground">{group.key}</p>
                                </div>
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={(event) =>
                                    setTargetForm((current) => ({
                                      ...current,
                                      group_keys: toggleTargetGroup(
                                        current.group_keys,
                                        group.key,
                                        event.target.checked,
                                      ),
                                    }))
                                  }
                                />
                              </label>
                            );
                          })}
                          {dashboard.notify_groups.length === 0 ? (
                            <p className="text-xs text-muted-foreground">
                              当前账号无分组列表权限，提交后将使用系统默认分组。
                            </p>
                          ) : null}
                        </div>
                      </DataField>
                      <div className="flex items-center justify-end gap-2 pt-1">
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => {
                            setShowAddTargetModal(false);
                            setEditingTarget(null);
                            setTargetFormError("");
                          }}
                        >
                          取消
                        </Button>
                        <Button
                          type="submit"
                          disabled={
                            (dashboard.notify_groups.length > 0 && targetForm.group_keys.length === 0) ||
                            (editingTarget ? !canTargetsUpdate : !canTargetsCreate)
                          }
                          title={
                            editingTarget
                              ? canTargetsUpdate
                                ? "提交编辑"
                                : "当前账号无编辑监控项权限"
                              : canTargetsCreate
                                ? "提交新增"
                                : "当前账号无新增监控项权限"
                          }
                        >
                          {editingTarget ? "保存修改" : "提交"}
                        </Button>
                      </div>
                    </form>
                  </CardContent>
                </Card>
                  </div>,
                  document.body,
                )
              : null}
          </section>
      </main>
    </div>
  );
}
