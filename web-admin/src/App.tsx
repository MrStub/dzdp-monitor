import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Boxes,
  Cable,
  CircleAlert,
  Link2,
  LogOut,
  Plus,
  RefreshCw,
  Settings2,
  ShieldCheck,
  UserCog,
  Waves,
} from "lucide-react";
import { apiRequest, getDefaultBaseUrl } from "@/lib/api";
import type {
  Dashboard,
  NoticeType,
  NotifyGroup,
  ProxyConfig,
  TargetItem,
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

type Notice = {
  type: NoticeType;
  message: string;
};

type LoadingState = {
  dashboard: boolean;
  targetSubmit: boolean;
  groupSubmit: boolean;
  pollSubmit: boolean;
  proxySubmit: boolean;
};

type TargetForm = {
  name: string;
  url: string;
  group_key: string;
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

type PermissionKey = (typeof PERMISSION_KEYS)[number];

type UserPermissions = Record<PermissionKey, boolean>;

type MockUser = {
  id: string;
  name: string;
  is_admin: boolean;
  permissions: UserPermissions;
};

type AuthSession = {
  is_logged_in: boolean;
  user_id: string;
};

type NavPermission = PermissionKey | "admin_only";

type NavItem = {
  id: TabId;
  label: string;
  icon: typeof Link2;
  hint: string;
  permission?: NavPermission;
};

const PERMISSION_LABELS: Record<PermissionKey, string> = {
  targets_read: "查看监控列表",
  targets_create: "新增监控项",
  targets_update: "编辑监控项",
  targets_delete: "删除监控项",
  webhook_manage: "管理通知分组",
  poll_manage: "管理轮询配置",
  proxy_manage: "管理代理配置",
};

const ALL_PERMISSIONS: UserPermissions = {
  targets_read: true,
  targets_create: true,
  targets_update: true,
  targets_delete: true,
  webhook_manage: true,
  poll_manage: true,
  proxy_manage: true,
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
  { id: "connection", label: "连接设置", icon: Link2, hint: "API 地址与鉴权" },
  {
    id: "groups",
    label: "通知分组",
    icon: Waves,
    hint: "分组与 webhook",
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

function getLocalValue(key: string, fallback: string) {
  return window.localStorage.getItem(key) ?? fallback;
}

function getLocalJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return fallback;
    }
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
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

function defaultUsers(): MockUser[] {
  return [
    {
      id: "admin",
      name: "管理员",
      is_admin: true,
      permissions: { ...ALL_PERMISSIONS },
    },
    {
      id: "operator",
      name: "运营同学",
      is_admin: false,
      permissions: { ...DEFAULT_OPERATOR_PERMISSIONS },
    },
  ];
}

function normalizeUsers(raw: unknown): MockUser[] {
  if (!Array.isArray(raw)) {
    return defaultUsers();
  }

  const normalized: MockUser[] = [];
  const ids = new Set<string>();
  for (const item of raw) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const row = item as Record<string, unknown>;
    const id = String(row.id || "").trim();
    if (!id || ids.has(id)) {
      continue;
    }
    ids.add(id);
    const isAdmin = Boolean(row.is_admin);
    normalized.push({
      id,
      name: String(row.name || id),
      is_admin: isAdmin,
      permissions: isAdmin
        ? { ...ALL_PERMISSIONS }
        : normalizePermissions(row.permissions, DEFAULT_OPERATOR_PERMISSIONS),
    });
  }

  if (!normalized.find((user) => user.id === "admin")) {
    normalized.unshift({
      id: "admin",
      name: "管理员",
      is_admin: true,
      permissions: { ...ALL_PERMISSIONS },
    });
  }
  if (!normalized.length) {
    return defaultUsers();
  }
  return normalized;
}

function normalizeAuthSession(raw: unknown): AuthSession {
  if (!raw || typeof raw !== "object") {
    return { is_logged_in: true, user_id: "admin" };
  }
  const source = raw as Record<string, unknown>;
  const userId = String(source.user_id || "admin");
  return {
    is_logged_in: Boolean(source.is_logged_in ?? true),
    user_id: userId || "admin",
  };
}

function createUserId(name: string, existing: Set<string>) {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  const base = slug || "user";
  let candidate = base;
  let idx = 2;
  while (existing.has(candidate)) {
    candidate = `${base}_${idx}`;
    idx += 1;
  }
  return candidate;
}

function createTargetForm(groupKey = ""): TargetForm {
  return { name: "", url: "", group_key: groupKey };
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
    <div className="grid gap-2.5">
      <Label className="leading-none">{label}</Label>
      {children}
      {hint ? <p className="text-xs leading-5 text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export default function App() {
  const [apiBaseUrl, setApiBaseUrl] = useState(() =>
    getLocalValue("dzdp_api_base_url", getDefaultBaseUrl()),
  );
  const [authToken, setAuthToken] = useState(() =>
    getLocalValue("dzdp_api_token", ""),
  );
  const [dashboard, setDashboard] = useState<Dashboard>(defaultDashboard);
  const [dashboardReady, setDashboardReady] = useState(false);
  const [notice, setNotice] = useState<Notice>({ type: "success", message: "" });
  const [loading, setLoading] = useState<LoadingState>({
    dashboard: false,
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
  const [groupForm, setGroupForm] = useState<GroupForm>(createGroupForm);
  const [proxyForm, setProxyForm] = useState<ProxyForm>(createProxyForm);
  const [users, setUsers] = useState<MockUser[]>(() =>
    normalizeUsers(getLocalJson("dzdp_mock_users", defaultUsers())),
  );
  const [authSession, setAuthSession] = useState<AuthSession>(() =>
    normalizeAuthSession(getLocalJson("dzdp_mock_auth_session", { is_logged_in: true, user_id: "admin" })),
  );
  const [loginUserId, setLoginUserId] = useState("admin");
  const [permissionUserId, setPermissionUserId] = useState("admin");
  const [newUserName, setNewUserName] = useState("");

  const currentUser = useMemo(() => {
    return users.find((user) => user.id === authSession.user_id) ?? users[0];
  }, [users, authSession.user_id]);

  const currentPermissions = useMemo<UserPermissions>(() => {
    if (!currentUser) {
      return { ...ALL_PERMISSIONS };
    }
    if (currentUser.is_admin) {
      return { ...ALL_PERMISSIONS };
    }
    return normalizePermissions(currentUser.permissions, DEFAULT_OPERATOR_PERMISSIONS);
  }, [currentUser]);

  const selectedPermissionUser = useMemo(
    () => users.find((user) => user.id === permissionUserId) ?? users[0],
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
    window.localStorage.setItem("dzdp_mock_users", JSON.stringify(users));
  }, [users]);

  useEffect(() => {
    window.localStorage.setItem("dzdp_mock_auth_session", JSON.stringify(authSession));
  }, [authSession]);

  useEffect(() => {
    if (!users.find((user) => user.id === authSession.user_id)) {
      setAuthSession((current) => ({ ...current, user_id: "admin" }));
    }
    if (!users.find((user) => user.id === loginUserId)) {
      setLoginUserId("admin");
    }
    if (!users.find((user) => user.id === permissionUserId)) {
      setPermissionUserId("admin");
    }
  }, [users, authSession.user_id, loginUserId, permissionUserId]);

  useEffect(() => {
    if (authSession.is_logged_in) {
      void loadDashboard();
      return;
    }
    setDashboardReady(false);
  }, [authSession.is_logged_in]);

  useEffect(() => {
    if (!notice.message) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setNotice((current) => ({ ...current, message: "" }));
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [notice.message]);

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
        hint: "最近一次轮询判定为 IN_STOCK",
        icon: Activity,
      },
      {
        label: "售罄状态",
        value: dashboard.summary.sold_out,
        hint: "最近一次轮询判定为 SOLD_OUT",
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

  function handleLogin() {
    const user = users.find((item) => item.id === loginUserId) ?? users[0];
    if (!user) {
      pushNotice("error", "没有可用用户，请先在 localStorage 恢复默认配置");
      return;
    }
    setAuthSession({ is_logged_in: true, user_id: user.id });
    setPermissionUserId(user.id);
    pushNotice("success", `已登录：${user.name}`);
  }

  function handleLogout() {
    setAuthSession((current) => ({ ...current, is_logged_in: false }));
    setShowAddTargetModal(false);
    setEditingTarget(null);
    pushNotice("success", "已退出登录");
  }

  function updateUserPermission(userId: string, key: PermissionKey, enabled: boolean) {
    setUsers((current) =>
      current.map((user) => {
        if (user.id !== userId || user.is_admin) {
          return user;
        }
        return {
          ...user,
          permissions: {
            ...user.permissions,
            [key]: enabled,
          },
        };
      }),
    );
  }

  function addMockUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canManagePermissions) {
      pushNotice("error", "仅管理员可新增用户");
      return;
    }
    const name = newUserName.trim();
    if (!name) {
      pushNotice("error", "请先输入用户名");
      return;
    }
    setUsers((current) => {
      const ids = new Set(current.map((user) => user.id));
      const id = createUserId(name, ids);
      const next = [
        ...current,
        {
          id,
          name,
          is_admin: false,
          permissions: { ...DEFAULT_OPERATOR_PERMISSIONS },
        },
      ];
      setPermissionUserId(id);
      setLoginUserId(id);
      return next;
    });
    setNewUserName("");
    pushNotice("success", `已新增用户：${name}`);
  }

  function removeMockUser(user: MockUser) {
    if (!canManagePermissions) {
      pushNotice("error", "仅管理员可删除用户");
      return;
    }
    if (user.is_admin || user.id === "admin") {
      pushNotice("error", "管理员账号不可删除");
      return;
    }
    if (!window.confirm(`删除用户「${user.name}」？`)) {
      return;
    }
    setUsers((current) => current.filter((item) => item.id !== user.id));
    if (authSession.user_id === user.id) {
      setAuthSession({ is_logged_in: true, user_id: "admin" });
    }
    pushNotice("success", `已删除用户：${user.name}`);
  }

  function applyDashboard(payload: Dashboard) {
    setDashboard(payload);
    setDashboardReady(true);
    setPollSeconds(payload.poll.interval_seconds || 60);
    setTargetForm((current) => {
      if (current.group_key || !payload.notify_groups.length) {
        return current;
      }
      return { ...current, group_key: payload.notify_groups[0].key };
    });
    setProxyForm(createProxyForm(payload.proxy));
  }

  async function loadDashboard() {
    setLoading((current) => ({ ...current, dashboard: true }));
    try {
      const payload = await request<Dashboard>("/api/dashboard");
      applyDashboard(payload);
      pushNotice("success", "面板已刷新");
    } catch (error) {
      const message = error instanceof Error ? error.message : "加载面板失败";
      setDashboardReady(false);
      pushNotice("error", message);
    } finally {
      setLoading((current) => ({ ...current, dashboard: false }));
    }
  }

  function saveConnection() {
    window.localStorage.setItem("dzdp_api_base_url", apiBaseUrl);
    window.localStorage.setItem("dzdp_api_token", authToken);
    void loadDashboard();
  }

  function openAddTargetModal() {
    if (!checkPermission("targets_create")) {
      return;
    }
    setEditingTarget(null);
    setTargetForm(createTargetForm(dashboard.notify_groups[0]?.key || ""));
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
      group_key: target.group_key,
    });
    setShowAddTargetModal(true);
  }

  async function submitTarget(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const permission = editingTarget ? "targets_update" : "targets_create";
    if (!checkPermission(permission)) {
      return;
    }
    setLoading((current) => ({ ...current, targetSubmit: true }));
    try {
      if (editingTarget) {
        await request(`/api/targets/${editingTarget.index}`, {
          method: "PATCH",
          body: JSON.stringify(targetForm),
        });
        pushNotice("success", `已更新套餐 #${editingTarget.index}`);
      } else {
        await request("/api/targets", {
          method: "POST",
          body: JSON.stringify(targetForm),
        });
        pushNotice("success", "已新增套餐");
      }
      setShowAddTargetModal(false);
      setEditingTarget(null);
      setTargetForm(createTargetForm(dashboard.notify_groups[0]?.key || ""));
      await loadDashboard();
    } catch (error) {
      pushNotice("error", error instanceof Error ? error.message : "提交套餐失败");
    } finally {
      setLoading((current) => ({ ...current, targetSubmit: false }));
    }
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

  const activeNavItem = navItems.find((item) => item.id === activeTab) ?? navItems[0];

  useEffect(() => {
    const currentItem = navItems.find((item) => item.id === activeTab);
    if (currentItem && hasNavAccess(currentItem.permission)) {
      return;
    }
    const fallback = navItems.find((item) => hasNavAccess(item.permission))?.id ?? "connection";
    setActiveTab(fallback);
  }, [activeTab, canManagePermissions, currentPermissions]);

  if (!authSession.is_logged_in) {
    return (
      <div className="app-shell glass-grid relative min-h-screen overflow-x-hidden">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-[radial-gradient(circle_at_top_right,rgba(244,115,74,0.22),transparent_45%)]" />
        <div className="pointer-events-none absolute bottom-0 left-0 h-72 w-72 rounded-full bg-[radial-gradient(circle,rgba(83,168,153,0.24),transparent_65%)] blur-3xl" />
        <main className="container relative z-10 py-8">
          <div className="mx-auto max-w-lg">
            <Card className="border-white/65 bg-white/88">
              <CardHeader>
                <CardTitle>登录后台</CardTitle>
                <CardDescription>纯前端 mock 登录，不调用后端鉴权接口。</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <DataField label="登录用户">
                  <Select value={loginUserId} onChange={(event) => setLoginUserId(event.target.value)}>
                    {users.map((user) => (
                      <option key={user.id} value={user.id}>
                        {user.name} ({user.id})
                      </option>
                    ))}
                  </Select>
                </DataField>
                <div className="flex gap-2">
                  <Button onClick={handleLogin}>登录（Mock）</Button>
                </div>
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

      <main className="container relative z-10 py-4 sm:py-6 lg:py-8">
        <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)] xl:grid-cols-[260px_minmax(0,1fr)]">
          <aside className="hidden lg:block">
            <div className="sticky top-6">
              <Card className="border-white/65 bg-white/88">
                <CardHeader className="space-y-0 border-b-0">
                  <div className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-secondary/70 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                    <Cable className="h-3.5 w-3.5" />
                    DZDP Console
                  </div>
                  <div className="space-y-1">
                    <CardTitle>后台管理</CardTitle>
                    <CardDescription>左侧导航固定，右侧切换内容区。</CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="grid gap-2">
                  {navItems.map((item) => {
                    const Icon = item.icon;
                    const active = item.id === activeTab;
                    const allowed = hasNavAccess(item.permission);
                    return (
                      <button
                        key={item.id}
                        type="button"
                        title={allowed ? item.hint : "当前账号无权限访问该模块"}
                        onClick={() => {
                          if (!allowed) {
                            pushNotice("error", "当前账号无权限访问该模块");
                            return;
                          }
                          setActiveTab(item.id);
                        }}
                        disabled={!allowed}
                        className={cn(
                          "flex min-w-0 items-center gap-3 rounded-xl border px-3.5 py-2.5 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25",
                          active
                            ? "border-primary/30 bg-primary/10 text-foreground"
                            : "border-border/50 bg-secondary/35 text-muted-foreground hover:border-border/80 hover:bg-secondary/60 hover:text-foreground",
                          !allowed && "cursor-not-allowed opacity-45",
                        )}
                      >
                        <Icon className="h-4 w-4 shrink-0" />
                        <span className="min-w-0">
                          <span className="block text-sm font-medium">{item.label}</span>
                          <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
                            {item.hint}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </CardContent>
              </Card>
            </div>
          </aside>

          <section className="min-w-0 space-y-4 pb-8">
            <Card className="border-white/65 bg-white/82 lg:hidden">
              <CardContent className="space-y-3 p-3">
                <div className="text-sm font-medium">功能切换</div>
                <div className="flex gap-2 overflow-x-auto pb-1">
                  {navItems.map((item) => {
                    const Icon = item.icon;
                    const active = item.id === activeTab;
                    const allowed = hasNavAccess(item.permission);
                    return (
                      <button
                        key={item.id}
                        type="button"
                        title={allowed ? item.hint : "当前账号无权限访问该模块"}
                        onClick={() => {
                          if (!allowed) {
                            pushNotice("error", "当前账号无权限访问该模块");
                            return;
                          }
                          setActiveTab(item.id);
                        }}
                        disabled={!allowed}
                        className={cn(
                          "inline-flex h-10 shrink-0 items-center gap-2 rounded-xl border px-3.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25",
                          active
                            ? "border-primary/35 bg-primary/10 text-foreground"
                            : "border-border/70 bg-background text-muted-foreground hover:border-border hover:bg-secondary/40",
                          !allowed && "cursor-not-allowed opacity-45",
                        )}
                      >
                        <Icon className="h-4 w-4 shrink-0" />
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {notice.message ? (
              <div
                className={cn(
                  "rounded-[1.4rem] border px-4 py-3 text-sm shadow-sm",
                  notice.type === "error"
                    ? "border-rose-200 bg-rose-50 text-rose-800"
                    : "border-emerald-200 bg-emerald-50 text-emerald-800",
                )}
              >
                {notice.message}
              </div>
            ) : null}

            <Card className="border-white/65 bg-white/72">
              <CardContent className="flex min-w-0 flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-1">
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                    {activeNavItem.label}
                  </p>
                  <p className="text-sm text-muted-foreground">{activeNavItem.hint}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="accent">{currentUser?.name || "未知用户"}</Badge>
                  <Button
                    variant="secondary"
                    onClick={() => void loadDashboard()}
                    disabled={loading.dashboard}
                    size="sm"
                  >
                    <RefreshCw className={cn("h-4 w-4", loading.dashboard && "animate-spin")} />
                    刷新面板
                  </Button>
                  <Button variant="outline" onClick={handleLogout} size="sm">
                    <LogOut className="h-4 w-4" />
                    退出登录
                  </Button>
                </div>
              </CardContent>
            </Card>

            {activeTab === "connection" ? (
              <section className="grid gap-4">
                <section className="grid gap-4 rounded-[2rem] border border-white/60 bg-hero p-4 shadow-panel sm:p-6 lg:grid-cols-2">
                  <div className="space-y-4">
                    <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">连接设置</h1>
                    <p className="text-sm leading-7 text-muted-foreground">
                      保留连接设置、套餐管理、分组管理、轮询设置和代理设置，前端仅重构为标准后台布局。
                    </p>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {summaryCards.map((card) => {
                        const Icon = card.icon;
                        return (
                          <Card key={card.label} className="bg-white/78">
                            <CardContent className="flex items-start justify-between p-4">
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

                  <Card className="bg-white/82">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Link2 className="h-5 w-5 text-primary" />
                        连接配置
                      </CardTitle>
                      <CardDescription>
                        API 地址与 Bearer Token 保存在浏览器 localStorage。
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <DataField label="API 地址">
                        <Input
                          value={apiBaseUrl}
                          placeholder="https://api.example.com"
                          onChange={(event) => setApiBaseUrl(event.target.value)}
                        />
                      </DataField>
                      <DataField
                        label="Bearer Token"
                        hint="服务端配置了 admin_api.auth_token 时必填。"
                      >
                        <Input
                          type="password"
                          value={authToken}
                          placeholder="可选"
                          onChange={(event) => setAuthToken(event.target.value)}
                        />
                      </DataField>
                      <div className="flex flex-wrap gap-3">
                        <Button onClick={saveConnection} disabled={loading.dashboard}>
                          {loading.dashboard ? "连接中..." : "保存并刷新"}
                        </Button>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                        <Badge variant={dashboardReady ? "success" : "danger"}>
                          {dashboardReady ? "已连接" : "未连接"}
                        </Badge>
                        {dashboard.admin_api.auth_token_configured ? (
                          <Badge variant="accent">服务端已启用鉴权</Badge>
                        ) : (
                          <Badge>服务端未启用鉴权</Badge>
                        )}
                        {dashboard.generated_at ? (
                          <span>最近刷新：{dashboard.generated_at}</span>
                        ) : null}
                      </div>
                    </CardContent>
                  </Card>
                </section>
              </section>
            ) : null}

            {activeTab === "targets" ? (
              <Card>
                <CardHeader className="pb-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="space-y-2">
                      <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                        Targets
                      </div>
                      <CardTitle>监控套餐</CardTitle>
                      <CardDescription>
                        首页主视图，支持快速新增与删除监控项。
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
                      当前账号没有 `targets_read` 权限，无法查看监控列表。
                    </div>
                  ) : (
                    <div className="grid gap-3">
                    {dashboard.targets.length ? (
                      dashboard.targets.map((target) => (
                        <div
                          key={`${target.activity_id}-${target.index}`}
                          className="rounded-[1.35rem] border border-border/70 bg-secondary/40 p-4"
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
                              <p className="text-sm text-muted-foreground">
                                {target.group_name || target.group_key} / {target.group_key}
                              </p>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
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
                              接口标题：{target.last_title}
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
                          {target.last_error_text ? (
                            <p className="mt-3 rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-700">
                              {target.last_error_text}
                            </p>
                          ) : null}
                        </div>
                      ))
                    ) : (
                      <div className="rounded-[1.35rem] border border-dashed border-border bg-secondary/30 p-5 text-sm text-muted-foreground">
                        还没有监控套餐，先新增一个。
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
                      Notify Routing
                    </div>
                    <CardTitle>通知分组</CardTitle>
                    <CardDescription>
                      套餐与分组绑定，默认分组和 webhook 都按后端现有协议写入。
                    </CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="space-y-5">
                  {!canWebhookManage ? (
                    <div className="rounded-[1.35rem] border border-dashed border-border bg-secondary/30 p-5 text-sm text-muted-foreground">
                      当前账号没有 `webhook_manage` 权限，通知分组处于只读状态。
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
                      <DataField label="分组 Key">
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
                    <DataField label="Webhook">
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
                          <span>保存时清空该分组的 webhook</span>
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
                        className="rounded-[1.35rem] border border-border/70 bg-secondary/40 p-4"
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
                          Webhook：{group.webhook_masked || "未配置"}
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
                      Polling
                    </div>
                    <CardTitle>轮询配置</CardTitle>
                    <CardDescription>
                      写回 `/api/poll`，保持与当前 Python 热更新逻辑一致。
                    </CardDescription>
                  </div>
                </CardHeader>
                <CardContent>
                  {!canPollManage ? (
                    <div className="mb-4 rounded-xl border border-dashed border-border bg-secondary/30 p-4 text-sm text-muted-foreground">
                      当前账号没有 `poll_manage` 权限，无法修改轮询配置。
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
                      Proxy Pool
                    </div>
                    <CardTitle>代理设置</CardTitle>
                    <CardDescription>
                      保持 `generic_json` provider 协议不变，仅优化表单录入体验。
                    </CardDescription>
                  </div>
                </CardHeader>
                <CardContent>
                  {!canProxyManage ? (
                    <div className="mb-4 rounded-xl border border-dashed border-border bg-secondary/30 p-4 text-sm text-muted-foreground">
                      当前账号没有 `proxy_manage` 权限，无法修改代理设置。
                    </div>
                  ) : null}
                  <form className="grid gap-4" onSubmit={submitProxy}>
                    <div className="grid gap-4 rounded-[1.4rem] bg-secondary/45 p-4 sm:grid-cols-3">
                      <label className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-white/75 px-4 py-3 sm:col-span-1">
                        <span className="text-sm font-medium">启用代理池</span>
                        <Switch
                          disabled={!canProxyManage}
                          checked={proxyForm.enabled}
                          onCheckedChange={(checked) =>
                            setProxyForm((current) => ({ ...current, enabled: checked }))
                          }
                        />
                      </label>
                      <DataField label="Provider">
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
                      <DataField label="API URL">
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
                      <DataField label="API Key Header">
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

                    <DataField label="API Key" hint="留空不会清除现有服务端 API Key。">
                      <Input
                        type="password"
                        disabled={!canProxyManage}
                        value={proxyForm.api_key}
                        placeholder={
                          dashboard.proxy.api_key_configured ? "服务端已配置，按需覆盖" : "保存时写入服务端配置"
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
                      <DataField label="Sticky 模式">
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
                          <option value="shared">shared</option>
                          <option value="per_target">per_target</option>
                        </Select>
                      </DataField>
                    </div>

                    <label className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-secondary/45 px-4 py-3 text-sm">
                      <span>验证代理池接口 SSL 证书</span>
                      <Switch
                        disabled={!canProxyManage}
                        checked={proxyForm.verify_ssl}
                        onCheckedChange={(checked) =>
                          setProxyForm((current) => ({ ...current, verify_ssl: checked }))
                        }
                      />
                    </label>

                    <div className="grid gap-4 lg:grid-cols-2">
                      <DataField label="extra_headers (JSON)">
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
                      <DataField label="query_params (JSON)">
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
                      <DataField label="request_body (JSON)">
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
                      <DataField label="response_fields (JSON)">
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

                    <DataField label="response_data_path">
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
                      <span className="text-sm text-muted-foreground">
                        这一块仍是 provider 接入入口，只改前端体验。
                      </span>
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
                      Access Control
                    </div>
                    <CardTitle>用户功能权限</CardTitle>
                    <CardDescription>
                      管理前端 mock 用户及其功能权限，配置写入 localStorage。
                    </CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="space-y-5">
                  {!canManagePermissions ? (
                    <div className="rounded-[1.35rem] border border-dashed border-border bg-secondary/30 p-5 text-sm text-muted-foreground">
                      当前账号不是管理员，无法进入权限配置。
                    </div>
                  ) : (
                    <>
                      <form className="flex flex-col gap-3 sm:flex-row" onSubmit={addMockUser}>
                        <Input
                          value={newUserName}
                          placeholder="新增普通用户，例如：客服同学"
                          onChange={(event) => setNewUserName(event.target.value)}
                        />
                        <Button type="submit">新增用户</Button>
                      </form>
                      <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
                        <div className="grid gap-3">
                          {users.map((user) => (
                            <button
                              key={user.id}
                              type="button"
                              onClick={() => setPermissionUserId(user.id)}
                              className={cn(
                                "rounded-xl border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25",
                                selectedPermissionUser?.id === user.id
                                  ? "border-primary/35 bg-primary/10"
                                  : "border-border/70 bg-secondary/40 hover:border-border hover:bg-secondary/55",
                              )}
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-medium">{user.name}</span>
                                <Badge variant={user.is_admin ? "accent" : "default"}>
                                  {user.is_admin ? "管理员" : "普通用户"}
                                </Badge>
                              </div>
                              <p className="mt-1 break-all text-xs text-muted-foreground">{user.id}</p>
                            </button>
                          ))}
                        </div>
                        {selectedPermissionUser ? (
                          <div className="space-y-4 rounded-xl border border-border/70 bg-secondary/35 p-4">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div>
                                <p className="text-sm font-semibold">{selectedPermissionUser.name}</p>
                                <p className="text-xs text-muted-foreground">
                                  用户 ID：{selectedPermissionUser.id}
                                </p>
                              </div>
                              <div className="flex items-center gap-2">
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  onClick={() => setLoginUserId(selectedPermissionUser.id)}
                                >
                                  设为登录默认
                                </Button>
                                <Button
                                  type="button"
                                  variant="destructive"
                                  size="sm"
                                  disabled={selectedPermissionUser.is_admin}
                                  onClick={() => removeMockUser(selectedPermissionUser)}
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
                                  <span>{permission}</span>
                                  <Switch
                                    disabled={selectedPermissionUser.is_admin}
                                    checked={
                                      selectedPermissionUser.is_admin
                                        ? true
                                        : Boolean(selectedPermissionUser.permissions[permission])
                                    }
                                    onCheckedChange={(checked) =>
                                      updateUserPermission(selectedPermissionUser.id, permission, checked)
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

            {showAddTargetModal ? (
              <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/35 p-4 sm:items-center">
                <Card className="z-50 my-6 w-full max-w-xl max-h-[90vh] overflow-y-auto">
                  <CardHeader className="pb-3">
                    <CardTitle>{editingTarget ? "编辑监控" : "新增监控"}</CardTitle>
                    <CardDescription>
                      仅需填写名字、链接、分组 key，提交后立即写入配置。
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
                          onChange={(event) =>
                            setTargetForm((current) => ({
                              ...current,
                              url: event.target.value,
                            }))
                          }
                        />
                      </DataField>
                      <DataField label="分组 (group_key)">
                        <Select
                          required
                          value={targetForm.group_key}
                          onChange={(event) =>
                            setTargetForm((current) => ({
                              ...current,
                              group_key: event.target.value,
                            }))
                          }
                        >
                          {dashboard.notify_groups.map((group) => (
                            <option key={group.key} value={group.key}>
                              {group.name} ({group.key})
                            </option>
                          ))}
                        </Select>
                      </DataField>
                      <div className="flex items-center justify-end gap-2 pt-1">
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => {
                            setShowAddTargetModal(false);
                            setEditingTarget(null);
                          }}
                        >
                          取消
                        </Button>
                        <Button
                          type="submit"
                          disabled={
                            loading.targetSubmit ||
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
                          {loading.targetSubmit
                            ? "提交中..."
                            : editingTarget
                              ? "保存修改"
                              : "提交"}
                        </Button>
                      </div>
                    </form>
                  </CardContent>
                </Card>
              </div>
            ) : null}
          </section>
        </div>
      </main>
    </div>
  );
}
