#!/usr/bin/env python3
import copy
import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

EPHEMERAL_QUERY_KEYS = {"shareid", "shareId"}
DEFAULT_GROUP_KEY = "default"
DEFAULT_GROUP_NAME = "默认分组"
MIN_INTERVAL_SECONDS = 5
DEFAULT_ADMIN_API_PORT = 8787
DEFAULT_PROXY_FIELDS = {
    "proxy_url": "proxy_url",
    "scheme": "scheme",
    "host": "host",
    "port": "port",
    "username": "username",
    "password": "password",
}
SQLITE_MONITOR_CONFIG_VERSION = 1


class ConfigError(ValueError):
    pass



def parse_activity_id(url: str, explicit_activity_id: Optional[str] = None) -> Optional[str]:
    if explicit_activity_id:
        return str(explicit_activity_id).strip()
    parsed = urlparse(str(url or ""))
    q = parse_qs(parsed.query)
    for key in ("activityid", "activityId"):
        if key in q and q[key]:
            return q[key][0].strip()
    return None



def normalize_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    https_index = raw.find("https://")
    if https_index >= 0:
        raw = raw[https_index:].strip()
    parsed = urlparse(raw)
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in EPHEMERAL_QUERY_KEYS
    ]
    normalized = parsed._replace(
        query=urlencode(filtered_query, doseq=True),
        fragment="",
    )
    return urlunparse(normalized)


def normalize_target_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    https_index = raw.find("https://")
    if https_index >= 0:
        raw = raw[https_index:].strip()
    parsed = urlparse(raw)
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in EPHEMERAL_QUERY_KEYS
    ]
    normalized = parsed._replace(
        query=urlencode(filtered_query, doseq=True),
        fragment="",
    )
    return urlunparse(normalized)



def slugify_key(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    return raw.strip("-")



def mask_secret(value: str) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]}"



def load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)



def save_config(path: str, data: Dict[str, Any]) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)



def ensure_poll(config: Dict[str, Any]) -> Dict[str, Any]:
    poll = config.get("poll")
    if not isinstance(poll, dict):
        config["poll"] = {}
        poll = config["poll"]
    return poll



def get_interval_seconds(config: Dict[str, Any]) -> int:
    poll = ensure_poll(config)
    raw = poll.get("interval_seconds", 60)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 60
    return max(MIN_INTERVAL_SECONDS, value)



def ensure_notify(config: Dict[str, Any]) -> Dict[str, Any]:
    notify = config.get("notify")
    if not isinstance(notify, dict):
        config["notify"] = {}
        notify = config["notify"]
    return notify



def ensure_email(notify: Dict[str, Any]) -> Dict[str, Any]:
    email = notify.get("email")
    if not isinstance(email, dict):
        notify["email"] = {
            "enabled": False,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "",
            "password": "",
            "from_addr": "",
            "to_addrs": ["you@example.com"],
            "use_tls": True,
            "use_ssl": False,
        }
        email = notify["email"]
    return email



def ensure_admin_api(config: Dict[str, Any]) -> Dict[str, Any]:
    admin_api = config.get("admin_api")
    if not isinstance(admin_api, dict):
        config["admin_api"] = {
            "listen_host": "127.0.0.1",
            "listen_port": DEFAULT_ADMIN_API_PORT,
            "cors_allowed_origins": [],
            "auth_token": "",
            "default_admin_username": "admin",
            "default_admin_password": "",
            "session_ttl_hours": 1440,
            "max_body_bytes": 1048576,
            "login_rate_limit": {
                "max_failures": 5,
                "window_seconds": 600,
                "block_seconds": 600,
            },
        }
        admin_api = config["admin_api"]
    admin_api.setdefault("listen_host", "127.0.0.1")
    admin_api.setdefault("listen_port", DEFAULT_ADMIN_API_PORT)
    admin_api.setdefault("auth_token", "")
    admin_api.setdefault("default_admin_username", "admin")
    admin_api.setdefault("default_admin_password", "")
    admin_api.setdefault("session_ttl_hours", 1440)
    admin_api.setdefault("max_body_bytes", 1048576)
    rate_limit = admin_api.get("login_rate_limit")
    if not isinstance(rate_limit, dict):
        admin_api["login_rate_limit"] = {}
        rate_limit = admin_api["login_rate_limit"]
    rate_limit.setdefault("max_failures", 5)
    rate_limit.setdefault("window_seconds", 600)
    rate_limit.setdefault("block_seconds", 600)
    origins = admin_api.get("cors_allowed_origins")
    if not isinstance(origins, list):
        admin_api["cors_allowed_origins"] = []
    return admin_api



def ensure_proxy(config: Dict[str, Any]) -> Dict[str, Any]:
    proxy = config.get("proxy")
    if not isinstance(proxy, dict):
        config["proxy"] = {}
        proxy = config["proxy"]

    proxy.setdefault("enabled", False)
    proxy.setdefault("provider", "generic_json")
    proxy.setdefault("request_method", "GET")
    proxy.setdefault("api_url", "")
    proxy.setdefault("api_key", "")
    proxy.setdefault("api_key_header", "X-API-Key")
    proxy.setdefault("extra_headers", {})
    proxy.setdefault("query_params", {})
    proxy.setdefault("request_body", {})
    proxy.setdefault("response_data_path", "")
    proxy.setdefault("response_fields", copy.deepcopy(DEFAULT_PROXY_FIELDS))
    proxy.setdefault("cache_seconds", 120)
    proxy.setdefault("timeout_seconds", 8)
    proxy.setdefault("sticky_mode", "shared")
    proxy.setdefault("verify_ssl", True)
    return proxy


def get_sqlite_path(config: Dict[str, Any]) -> str:
    return str(config.get("sqlite_path") or "data/monitor_state.db")


def _connect_sqlite(config: Dict[str, Any]) -> sqlite3.Connection:
    db_path = get_sqlite_path(config)
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_monitor_config_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitor_config_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitor_notify_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            webhook TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitor_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            group_keys_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    existing_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(monitor_targets)")}
    if "enabled" not in existing_columns:
        conn.execute("ALTER TABLE monitor_targets ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")


def _get_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM monitor_config_settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    return str(row["value"])


def _set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO monitor_config_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, str(value)),
    )


def _encode_group_keys(group_keys: List[str]) -> str:
    return json.dumps(_clean_group_key_list(group_keys), ensure_ascii=False)


def _decode_group_keys(raw: Any) -> List[str]:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = []
    elif isinstance(raw, list):
        parsed = raw
    else:
        parsed = []
    if not isinstance(parsed, list):
        return []
    return _clean_group_key_list(parsed)


def _db_group_keys(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute("SELECT key FROM monitor_notify_groups ORDER BY sort_order ASC, id ASC").fetchall()
    return [str(row["key"]) for row in rows]


def _db_default_group_key(conn: sqlite3.Connection) -> str:
    configured = slugify_key(_get_setting(conn, "default_group_key") or "")
    keys = _db_group_keys(conn)
    if configured and configured in keys:
        return configured
    fallback = keys[0] if keys else DEFAULT_GROUP_KEY
    _set_setting(conn, "default_group_key", fallback)
    return fallback


def _db_target_rows(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, activity_id, name, url, group_keys_json, enabled
        FROM monitor_targets
        ORDER BY id ASC
        """
    ).fetchall()
    result: List[Dict[str, Any]] = []
    for row in rows:
        group_keys = _decode_group_keys(row["group_keys_json"])
        result.append(
            {
                "id": int(row["id"]),
                "activity_id": str(row["activity_id"] or "").strip(),
                "name": str(row["name"] or "").strip(),
                "url": normalize_target_url(str(row["url"] or "")),
                "group_keys": group_keys,
                "group_key": group_keys[0] if group_keys else DEFAULT_GROUP_KEY,
                "enabled": bool(int(row["enabled"] or 0)),
            }
        )
    return result


def ensure_sqlite_monitor_config(config: Dict[str, Any]) -> bool:
    conn = _connect_sqlite(config)
    try:
        _ensure_monitor_config_schema(conn)
        _set_setting(conn, "schema_version", str(SQLITE_MONITOR_CONFIG_VERSION))

        groups_count = int(conn.execute("SELECT COUNT(*) AS c FROM monitor_notify_groups").fetchone()["c"])
        targets_count = int(conn.execute("SELECT COUNT(*) AS c FROM monitor_targets").fetchone()["c"])
        changed = False

        if groups_count == 0:
            groups = ensure_feishu_groups(config)
            for idx, group in enumerate(groups, start=1):
                conn.execute(
                    """
                    INSERT INTO monitor_notify_groups (key, name, webhook, sort_order)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        group_key(group),
                        group_name(group),
                        group_webhook(group),
                        idx,
                    ),
                )
            default_group_key = slugify_key(str(ensure_notify(config).get("default_group_key", DEFAULT_GROUP_KEY))) or DEFAULT_GROUP_KEY
            valid_group_keys = {group_key(group) for group in groups}
            if default_group_key not in valid_group_keys:
                default_group_key = groups[0]["key"] if groups else DEFAULT_GROUP_KEY
            _set_setting(conn, "default_group_key", default_group_key)
            changed = True
        else:
            _db_default_group_key(conn)

        if targets_count == 0:
            normalize_targets_in_place(config)
            valid_group_keys = set(_db_group_keys(conn))
            fallback_group = _db_default_group_key(conn)
            for target in ensure_targets(config):
                activity_id = target_activity_id(target)
                if not activity_id:
                    continue
                normalized_group_keys = [key for key in target_group_keys(target, config) if key in valid_group_keys]
                if not normalized_group_keys:
                    normalized_group_keys = [fallback_group]
                conn.execute(
                    """
                    INSERT INTO monitor_targets (activity_id, name, url, group_keys_json, enabled)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (
                        activity_id,
                        target_name(target) or f"target-{activity_id}",
                        target_url(target),
                        _encode_group_keys(normalized_group_keys),
                    ),
                )
            changed = True

        conn.commit()
        return changed
    finally:
        conn.close()


def group_key(group: Dict[str, Any]) -> str:
    return str(group.get("key", "")).strip()



def group_name(group: Dict[str, Any]) -> str:
    return str(group.get("name", "")).strip()



def group_webhook(group: Dict[str, Any]) -> str:
    return str(group.get("webhook", "")).strip()



def ensure_feishu_groups(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    notify = ensure_notify(config)
    ensure_email(notify)
    groups = notify.get("feishu_groups")
    if not isinstance(groups, list):
        notify["feishu_groups"] = []
        groups = notify["feishu_groups"]

    legacy_webhook = str(notify.get("feishu_webhook", "")).strip()
    normalized: List[Dict[str, Any]] = []
    seen_keys = set()

    def append_group(raw_group: Dict[str, Any], fallback_index: int) -> None:
        key = slugify_key(raw_group.get("key") or raw_group.get("name") or "")
        if not key:
            key = DEFAULT_GROUP_KEY if fallback_index == 1 else f"group-{fallback_index}"
        if key in seen_keys:
            suffix = 2
            base_key = key
            while key in seen_keys:
                key = f"{base_key}-{suffix}"
                suffix += 1
        name = str(raw_group.get("name") or (DEFAULT_GROUP_NAME if key == DEFAULT_GROUP_KEY else key)).strip()
        webhook = str(raw_group.get("webhook", "")).strip()
        normalized.append({"key": key, "name": name, "webhook": webhook})
        seen_keys.add(key)

    for index, raw_group in enumerate(groups, start=1):
        if not isinstance(raw_group, dict):
            continue
        append_group(raw_group, index)

    if legacy_webhook:
        default_existing = next((g for g in normalized if g["key"] == DEFAULT_GROUP_KEY), None)
        if default_existing:
            if not default_existing["webhook"]:
                default_existing["webhook"] = legacy_webhook
        else:
            normalized.insert(0, {"key": DEFAULT_GROUP_KEY, "name": DEFAULT_GROUP_NAME, "webhook": legacy_webhook})

    if not normalized:
        normalized.append({"key": DEFAULT_GROUP_KEY, "name": DEFAULT_GROUP_NAME, "webhook": ""})

    notify["feishu_groups"] = normalized
    notify.setdefault("default_group_key", DEFAULT_GROUP_KEY)
    default_group_key = slugify_key(str(notify.get("default_group_key") or DEFAULT_GROUP_KEY)) or DEFAULT_GROUP_KEY
    if default_group_key not in {g["key"] for g in normalized}:
        default_group_key = normalized[0]["key"]
    notify["default_group_key"] = default_group_key
    return notify["feishu_groups"]



def get_group_keys(config: Dict[str, Any]) -> List[str]:
    return [group["key"] for group in ensure_feishu_groups(config)]



def ensure_targets(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    targets = config.get("targets")
    if not isinstance(targets, list):
        config["targets"] = []
        targets = config["targets"]
    return targets



def target_activity_id(target: Dict[str, Any]) -> Optional[str]:
    return parse_activity_id(str(target.get("url", "")), target.get("activity_id"))



def target_name(target: Dict[str, Any]) -> str:
    return str(target.get("name", "")).strip()



def target_url(target: Dict[str, Any]) -> str:
    return normalize_target_url(str(target.get("url", "")))


def _clean_group_key_list(values: List[Any]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for value in values:
        key = slugify_key(str(value or "").strip())
        if not key or key in seen:
            continue
        normalized.append(key)
        seen.add(key)
    return normalized


def target_group_keys(target: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> List[str]:
    raw_values = target.get("group_keys")
    normalized: List[str] = []
    if isinstance(raw_values, list):
        normalized = _clean_group_key_list(raw_values)
    if not normalized:
        legacy_raw = str(target.get("group_key") or target.get("notify_group_key") or "").strip()
        if legacy_raw:
            normalized = _clean_group_key_list([legacy_raw])
    if normalized:
        return normalized
    if config is not None:
        return [str(ensure_notify(config).get("default_group_key", DEFAULT_GROUP_KEY))]
    return [DEFAULT_GROUP_KEY]



def target_group_key(target: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> str:
    return target_group_keys(target, config)[0]



def normalize_targets_in_place(config: Dict[str, Any]) -> bool:
    targets = ensure_targets(config)
    valid_group_keys = set(get_group_keys(config))
    default_group = str(ensure_notify(config).get("default_group_key", DEFAULT_GROUP_KEY))
    changed = False
    for target in targets:
        normalized_name = target_name(target)
        normalized_url = target_url(target)
        normalized_activity_id = parse_activity_id(normalized_url, target.get("activity_id"))
        normalized_group_keys = [
            group_key_value
            for group_key_value in target_group_keys(target, config)
            if group_key_value in valid_group_keys
        ]
        if not normalized_group_keys:
            normalized_group_keys = [default_group]

        if target.get("name") != normalized_name:
            target["name"] = normalized_name
            changed = True
        if target.get("url") != normalized_url:
            target["url"] = normalized_url
            changed = True
        if normalized_activity_id and str(target.get("activity_id", "")).strip() != normalized_activity_id:
            target["activity_id"] = normalized_activity_id
            changed = True
        if target.get("group_keys") != normalized_group_keys:
            target["group_keys"] = normalized_group_keys
            changed = True
        if "group_key" in target:
            target.pop("group_key", None)
            changed = True
        if "notify_group_key" in target:
            target.pop("notify_group_key", None)
            changed = True
    return changed



def normalize_config_in_place(config: Dict[str, Any]) -> bool:
    before = json.dumps(config, ensure_ascii=False, sort_keys=True)
    ensure_poll(config)
    ensure_notify(config)
    ensure_email(config["notify"])
    ensure_feishu_groups(config)
    ensure_proxy(config)
    ensure_admin_api(config)
    normalize_targets_in_place(config)
    ensure_sqlite_monitor_config(config)
    after = json.dumps(config, ensure_ascii=False, sort_keys=True)
    return before != after



def list_targets(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    normalize_config_in_place(config)
    conn = _connect_sqlite(config)
    try:
        _ensure_monitor_config_schema(conn)
        rows = _db_target_rows(conn)
        for idx, row in enumerate(rows, start=1):
            row["index"] = idx
            row.pop("id", None)
        return rows
    finally:
        conn.close()



def find_target_index(targets: List[Dict[str, Any]], activity_id: str) -> int:
    wanted = str(activity_id).strip()
    for idx, target in enumerate(targets):
        if target_activity_id(target) == wanted:
            return idx
    return -1



def find_target_indexes_by_name(targets: List[Dict[str, Any]], name: str) -> List[int]:
    wanted = str(name).strip()
    return [idx for idx, target in enumerate(targets) if target_name(target) == wanted]



def find_target_indexes_by_url(targets: List[Dict[str, Any]], url: str) -> List[int]:
    wanted = normalize_url(url)
    return [idx for idx, target in enumerate(targets) if normalize_url(str(target.get("url", ""))) == wanted]



def build_not_found_message(
    *,
    activity_id: Optional[str],
    index: Optional[int],
    name: Optional[str],
    url: Optional[str],
) -> str:
    if activity_id:
        return f"Target not found: activity_id={activity_id}"
    if index is not None:
        return f"Target not found: index={index}"
    if name:
        return f"Target not found: name={name}"
    return f"Target not found: url={normalize_url(url or '')}"



def resolve_target_index(
    targets: List[Dict[str, Any]],
    *,
    activity_id: Optional[str] = None,
    index: Optional[int] = None,
    name: Optional[str] = None,
    url: Optional[str] = None,
) -> Tuple[int, Optional[str]]:
    if activity_id:
        found = find_target_index(targets, activity_id)
        if found >= 0:
            return found, None
        return -1, build_not_found_message(activity_id=activity_id, index=index, name=name, url=url)
    if index is not None:
        if 1 <= index <= len(targets):
            return index - 1, None
        return -1, build_not_found_message(activity_id=activity_id, index=index, name=name, url=url)
    if name:
        matched = find_target_indexes_by_name(targets, name)
        if len(matched) == 1:
            return matched[0], None
        if len(matched) > 1:
            return -1, f"Multiple targets match name={name}. Please use index or activity_id."
        return -1, build_not_found_message(activity_id=activity_id, index=index, name=name, url=url)
    if url:
        matched = find_target_indexes_by_url(targets, url)
        if len(matched) == 1:
            return matched[0], None
        if len(matched) > 1:
            return -1, f"Multiple targets match url={normalize_url(url)}. Please use index."
        return -1, build_not_found_message(activity_id=activity_id, index=index, name=name, url=url)
    return -1, "One selector is required: --activity-id / --index / --name / --url"



def ensure_target_name_unique(targets: List[Dict[str, Any]], name: str, current_index: Optional[int] = None) -> None:
    matched = find_target_indexes_by_name(targets, name)
    filtered = [idx for idx in matched if current_index is None or idx != current_index]
    if filtered:
        raise ConfigError(f"Target name already exists: name={name}")



def ensure_group_exists(config: Dict[str, Any], group_key_value: Optional[str]) -> str:
    conn = _connect_sqlite(config)
    try:
        _ensure_monitor_config_schema(conn)
        valid_keys = set(_db_group_keys(conn))
        fallback_key = _db_default_group_key(conn)
        normalized = slugify_key(group_key_value or "") or fallback_key
        if normalized not in valid_keys:
            raise ConfigError(f"Unknown notify group: {group_key_value}")
        return normalized
    finally:
        conn.close()


def ensure_groups_exist(
    config: Dict[str, Any],
    group_keys_values: Optional[List[Any]] = None,
    group_key_value: Optional[str] = None,
) -> List[str]:
    conn = _connect_sqlite(config)
    try:
        _ensure_monitor_config_schema(conn)
        valid_keys = set(_db_group_keys(conn))
        fallback_key = _db_default_group_key(conn)
        candidates: List[Any] = []
        if isinstance(group_keys_values, list):
            candidates.extend(group_keys_values)
        elif group_keys_values is not None:
            candidates.append(group_keys_values)
        if not candidates and group_key_value is not None:
            candidates.append(group_key_value)
        normalized = _clean_group_key_list(candidates)
        if not normalized:
            normalized = [fallback_key]
        for key in normalized:
            if key not in valid_keys:
                raise ConfigError(f"Unknown notify group: {key}")
        return normalized
    finally:
        conn.close()



def add_target(
    config: Dict[str, Any],
    *,
    url: str,
    name: Optional[str],
    activity_id: Optional[str],
    group_keys_values: Optional[List[Any]],
    group_key_value: Optional[str],
    enabled: Optional[bool],
    upsert: bool,
) -> Dict[str, Any]:
    normalize_config_in_place(config)
    conn = _connect_sqlite(config)
    try:
        _ensure_monitor_config_schema(conn)
        targets = _db_target_rows(conn)
        normalized_url = normalize_target_url(url)
        aid = parse_activity_id(normalized_url, activity_id)
        if not aid:
            raise ConfigError("Cannot parse activity_id from url. Please pass activity_id explicitly.")
        final_name = str(name or f"target-{aid}").strip()
        if not final_name:
            raise ConfigError("Target name cannot be empty.")
        final_group_keys = ensure_groups_exist(config, group_keys_values, group_key_value)
        final_enabled = True if enabled is None else bool(enabled)
        idx = find_target_index(targets, aid)
        ensure_target_name_unique(targets, final_name, current_index=idx if idx >= 0 else None)
        new_obj = {
            "name": final_name,
            "url": normalized_url,
            "activity_id": aid,
            "group_keys": final_group_keys,
            "enabled": final_enabled,
        }
        if idx >= 0:
            if not upsert:
                raise ConfigError(f"Target already exists: activity_id={aid}")
            conn.execute(
                """
                UPDATE monitor_targets
                SET name = ?, url = ?, group_keys_json = ?, enabled = ?
                WHERE activity_id = ?
                """,
                (final_name, normalized_url, _encode_group_keys(final_group_keys), int(final_enabled), aid),
            )
            action = "updated"
        else:
            conn.execute(
                """
                INSERT INTO monitor_targets (activity_id, name, url, group_keys_json, enabled)
                VALUES (?, ?, ?, ?, ?)
                """,
                (aid, final_name, normalized_url, _encode_group_keys(final_group_keys), int(final_enabled)),
            )
            action = "added"
        conn.commit()
        total = int(conn.execute("SELECT COUNT(*) AS c FROM monitor_targets").fetchone()["c"])
        return {
            "action": action,
            "target": {
                **new_obj,
                "group_key": final_group_keys[0],
            },
            "total": total,
        }
    finally:
        conn.close()



def update_target(
    config: Dict[str, Any],
    *,
    activity_id: Optional[str],
    index: Optional[int],
    selector_name: Optional[str],
    selector_url: Optional[str],
    set_name: Optional[str],
    set_url: Optional[str],
    new_activity_id: Optional[str],
    set_group_keys: Optional[List[Any]],
    set_group_key: Optional[str],
    set_enabled: Optional[bool],
) -> Dict[str, Any]:
    normalize_config_in_place(config)
    conn = _connect_sqlite(config)
    try:
        _ensure_monitor_config_schema(conn)
        targets = _db_target_rows(conn)
        idx, err = resolve_target_index(
            targets,
            activity_id=activity_id,
            index=index,
            name=selector_name,
            url=selector_url,
        )
        if idx < 0:
            raise ConfigError(err or "Target not found")
        if (
            set_name is None
            and set_url is None
            and new_activity_id is None
            and set_group_keys is None
            and set_group_key is None
            and set_enabled is None
        ):
            raise ConfigError("No update fields provided.")

        cur = dict(targets[idx])
        target_row_id = int(cur["id"])
        current_activity_id = target_activity_id(cur) or ""
        final_url = normalize_target_url(set_url) if set_url is not None else target_url(cur)
        parsed_from_url = parse_activity_id(final_url)
        final_activity_id = str(new_activity_id).strip() if new_activity_id else (parsed_from_url or current_activity_id)
        if not final_activity_id:
            raise ConfigError("Cannot determine final activity_id.")
        if final_activity_id != current_activity_id:
            existing_idx = find_target_index(targets, final_activity_id)
            if existing_idx >= 0 and existing_idx != idx:
                raise ConfigError(f"Cannot update: target with activity_id={final_activity_id} already exists.")
        if set_name is not None:
            final_name = str(set_name).strip()
            if not final_name:
                raise ConfigError("Target name cannot be empty.")
            ensure_target_name_unique(targets, final_name, current_index=idx)
            cur["name"] = final_name
        if set_url is not None:
            cur["url"] = final_url
        if set_group_keys is not None or set_group_key is not None:
            cur["group_keys"] = ensure_groups_exist(config, set_group_keys, set_group_key)
            cur.pop("group_key", None)
        if set_enabled is not None:
            cur["enabled"] = bool(set_enabled)
        cur["activity_id"] = final_activity_id
        final_group_keys = target_group_keys(cur, config)
        conn.execute(
            """
            UPDATE monitor_targets
            SET activity_id = ?, name = ?, url = ?, group_keys_json = ?, enabled = ?
            WHERE id = ?
            """,
            (
                final_activity_id,
                target_name(cur),
                target_url(cur),
                _encode_group_keys(final_group_keys),
                int(bool(cur.get("enabled", True))),
                target_row_id,
            ),
        )
        if set_enabled is not None:
            try:
                if bool(set_enabled):
                    conn.execute(
                        """
                        UPDATE target_state
                        SET disabled_reason = NULL, consecutive_null_brief_count = 0
                        WHERE activity_id = ?
                        """,
                        (final_activity_id,),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE target_state
                        SET disabled_reason = 'manually_disabled'
                        WHERE activity_id = ?
                        """,
                        (final_activity_id,),
                    )
            except sqlite3.OperationalError:
                pass
        conn.commit()
        return {
            "action": "updated",
            "old_activity_id": current_activity_id,
            "target": {
                "index": idx + 1,
                "activity_id": target_activity_id(cur),
                "name": target_name(cur),
                "url": target_url(cur),
                "group_keys": target_group_keys(cur, config),
                "group_key": target_group_key(cur, config),
                "enabled": bool(cur.get("enabled", True)),
            },
        }
    finally:
        conn.close()



def remove_target(
    config: Dict[str, Any],
    *,
    activity_id: Optional[str],
    index: Optional[int],
    name: Optional[str],
    url: Optional[str],
) -> Dict[str, Any]:
    normalize_config_in_place(config)
    conn = _connect_sqlite(config)
    try:
        _ensure_monitor_config_schema(conn)
        targets = _db_target_rows(conn)
        idx, err = resolve_target_index(
            targets,
            activity_id=activity_id,
            index=index,
            name=name,
            url=url,
        )
        if idx < 0:
            raise ConfigError(err or "Target not found")
        removed = dict(targets[idx])
        removed_row_id = int(removed["id"])
        conn.execute("DELETE FROM monitor_targets WHERE id = ?", (removed_row_id,))
        conn.commit()
        total = int(conn.execute("SELECT COUNT(*) AS c FROM monitor_targets").fetchone()["c"])
        return {
            "action": "removed",
            "target": {
                "index": idx + 1,
                "activity_id": target_activity_id(removed),
                "name": target_name(removed),
                "url": target_url(removed),
                "group_keys": target_group_keys(removed, config),
                "group_key": target_group_key(removed, config),
            },
            "total": total,
        }
    finally:
        conn.close()



def find_group_index(groups: List[Dict[str, Any]], key_value: str) -> int:
    wanted = slugify_key(key_value) or str(key_value or "").strip()
    for idx, group in enumerate(groups):
        if group_key(group) == wanted:
            return idx
    return -1



def list_notify_groups(config: Dict[str, Any], include_secret: bool = False) -> List[Dict[str, Any]]:
    normalize_config_in_place(config)
    conn = _connect_sqlite(config)
    try:
        _ensure_monitor_config_schema(conn)
        default_group_key = _db_default_group_key(conn)
        rows = conn.execute(
            """
            SELECT key, name, webhook
            FROM monitor_notify_groups
            ORDER BY sort_order ASC, id ASC
            """
        ).fetchall()
        groups = []
        for row in rows:
            webhook = str(row["webhook"] or "").strip()
            groups.append(
                {
                    "key": str(row["key"] or "").strip(),
                    "name": str(row["name"] or "").strip(),
                    "is_default": str(row["key"] or "").strip() == default_group_key,
                    "webhook": webhook if include_secret else "",
                    "webhook_masked": mask_secret(webhook),
                    "webhook_configured": bool(webhook),
                }
            )
        return groups
    finally:
        conn.close()



def add_notify_group(config: Dict[str, Any], *, key_value: Optional[str], name: str, webhook: str) -> Dict[str, Any]:
    normalize_config_in_place(config)
    conn = _connect_sqlite(config)
    try:
        _ensure_monitor_config_schema(conn)
        groups = conn.execute("SELECT key FROM monitor_notify_groups ORDER BY sort_order ASC, id ASC").fetchall()
        final_name = str(name or "").strip()
        if not final_name:
            raise ConfigError("Group name cannot be empty.")
        base_key = slugify_key(key_value or final_name)
        if not base_key:
            base_key = f"group-{len(groups) + 1}"
        final_key = base_key
        suffix = 2
        existing_keys = {str(row["key"]) for row in groups}
        while final_key in existing_keys:
            final_key = f"{base_key}-{suffix}"
            suffix += 1
        final_webhook = str(webhook or "").strip()
        max_sort_order_row = conn.execute("SELECT COALESCE(MAX(sort_order), 0) AS max_order FROM monitor_notify_groups").fetchone()
        next_sort_order = int(max_sort_order_row["max_order"]) + 1
        conn.execute(
            """
            INSERT INTO monitor_notify_groups (key, name, webhook, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            (final_key, final_name, final_webhook, next_sort_order),
        )
        conn.commit()
        total = int(conn.execute("SELECT COUNT(*) AS c FROM monitor_notify_groups").fetchone()["c"])
        return {
            "action": "added",
            "group": {
                "key": final_key,
                "name": final_name,
                "webhook_masked": mask_secret(final_webhook),
                "webhook_configured": bool(final_webhook),
                "is_default": False,
            },
            "total": total,
        }
    finally:
        conn.close()



def update_notify_group(
    config: Dict[str, Any],
    *,
    key_value: str,
    set_name: Optional[str],
    set_webhook: Optional[str],
    make_default: Optional[bool],
) -> Dict[str, Any]:
    normalize_config_in_place(config)
    conn = _connect_sqlite(config)
    try:
        _ensure_monitor_config_schema(conn)
        normalized_key = slugify_key(key_value) or str(key_value or "").strip()
        row = conn.execute(
            "SELECT id, key, name, webhook FROM monitor_notify_groups WHERE key = ?",
            (normalized_key,),
        ).fetchone()
        if not row:
            raise ConfigError(f"Notify group not found: key={key_value}")
        if set_name is None and set_webhook is None and make_default is None:
            raise ConfigError("No update fields provided.")
        group_key_value = str(row["key"] or "").strip()
        group_name_value = str(row["name"] or "").strip()
        group_webhook_value = str(row["webhook"] or "").strip()
        if set_name is not None:
            final_name = str(set_name).strip()
            if not final_name:
                raise ConfigError("Group name cannot be empty.")
            group_name_value = final_name
        if set_webhook is not None:
            group_webhook_value = str(set_webhook or "").strip()
        conn.execute(
            """
            UPDATE monitor_notify_groups
            SET name = ?, webhook = ?
            WHERE key = ?
            """,
            (group_name_value, group_webhook_value, group_key_value),
        )
        if make_default:
            _set_setting(conn, "default_group_key", group_key_value)
        default_group_key = _db_default_group_key(conn)
        conn.commit()
        return {
            "action": "updated",
            "group": {
                "key": group_key_value,
                "name": group_name_value,
                "webhook_masked": mask_secret(group_webhook_value),
                "webhook_configured": bool(group_webhook_value),
                "is_default": group_key_value == default_group_key,
            },
        }
    finally:
        conn.close()



def remove_notify_group(config: Dict[str, Any], *, key_value: str) -> Dict[str, Any]:
    normalize_config_in_place(config)
    conn = _connect_sqlite(config)
    try:
        _ensure_monitor_config_schema(conn)
        normalized_key = slugify_key(key_value) or str(key_value or "").strip()
        groups = conn.execute(
            """
            SELECT id, key, name
            FROM monitor_notify_groups
            ORDER BY sort_order ASC, id ASC
            """
        ).fetchall()
        if not groups:
            raise ConfigError("Notify groups is empty.")
        group_rows = [dict(row) for row in groups]
        idx = next((i for i, row in enumerate(group_rows) if str(row["key"]) == normalized_key), -1)
        if idx < 0:
            raise ConfigError(f"Notify group not found: key={key_value}")
        if len(group_rows) == 1:
            raise ConfigError("Cannot remove the last notify group.")

        removed = group_rows[idx]
        remaining = [row for row in group_rows if int(row["id"]) != int(removed["id"])]
        default_group_key = _db_default_group_key(conn)
        reassigned_group_key = default_group_key
        if removed["key"] == default_group_key:
            reassigned_group_key = str(remaining[0]["key"])
            _set_setting(conn, "default_group_key", reassigned_group_key)

        target_rows = conn.execute("SELECT id, group_keys_json FROM monitor_targets").fetchall()
        for row in target_rows:
            current_keys = _decode_group_keys(row["group_keys_json"])
            if str(removed["key"]) not in current_keys:
                continue
            next_keys = [key for key in current_keys if key != str(removed["key"])]
            if not next_keys:
                next_keys = [reassigned_group_key]
            conn.execute(
                "UPDATE monitor_targets SET group_keys_json = ? WHERE id = ?",
                (_encode_group_keys(next_keys), int(row["id"])),
            )

        conn.execute("DELETE FROM monitor_notify_groups WHERE id = ?", (int(removed["id"]),))
        conn.commit()
        total = int(conn.execute("SELECT COUNT(*) AS c FROM monitor_notify_groups").fetchone()["c"])
        return {
            "action": "removed",
            "group": {
                "key": str(removed["key"]),
                "name": str(removed["name"]),
            },
            "reassigned_group_key": reassigned_group_key,
            "total": total,
        }
    finally:
        conn.close()



def get_proxy_config_for_api(config: Dict[str, Any]) -> Dict[str, Any]:
    normalize_config_in_place(config)
    proxy = ensure_proxy(config)
    return {
        "enabled": bool(proxy.get("enabled", False)),
        "provider": str(proxy.get("provider", "generic_json")),
        "request_method": str(proxy.get("request_method", "GET")),
        "api_url": str(proxy.get("api_url", "")),
        "api_key_header": str(proxy.get("api_key_header", "X-API-Key")),
        "api_key_configured": bool(str(proxy.get("api_key", "")).strip()),
        "api_key_masked": mask_secret(str(proxy.get("api_key", ""))),
        "extra_headers": dict(proxy.get("extra_headers") or {}),
        "query_params": dict(proxy.get("query_params") or {}),
        "request_body": dict(proxy.get("request_body") or {}),
        "response_data_path": str(proxy.get("response_data_path", "")),
        "response_fields": dict(proxy.get("response_fields") or DEFAULT_PROXY_FIELDS),
        "cache_seconds": int(proxy.get("cache_seconds", 120) or 120),
        "timeout_seconds": int(proxy.get("timeout_seconds", 8) or 8),
        "sticky_mode": str(proxy.get("sticky_mode", "shared")),
        "verify_ssl": bool(proxy.get("verify_ssl", True)),
    }



def update_proxy_config(config: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    normalize_config_in_place(config)
    proxy = ensure_proxy(config)
    for field in (
        "enabled",
        "provider",
        "request_method",
        "api_url",
        "api_key_header",
        "cache_seconds",
        "timeout_seconds",
        "sticky_mode",
        "verify_ssl",
        "response_data_path",
    ):
        if field in payload:
            proxy[field] = payload[field]
    for field in ("extra_headers", "query_params", "request_body", "response_fields"):
        if field in payload and isinstance(payload[field], dict):
            proxy[field] = payload[field]
    if "api_key" in payload:
        proxy["api_key"] = str(payload.get("api_key") or "").strip()
    return get_proxy_config_for_api(config)



def get_admin_api_config_for_api(config: Dict[str, Any]) -> Dict[str, Any]:
    admin_api = ensure_admin_api(config)
    return {
        "listen_host": str(admin_api.get("listen_host", "127.0.0.1")),
        "listen_port": int(admin_api.get("listen_port", DEFAULT_ADMIN_API_PORT)),
        "cors_allowed_origins": list(admin_api.get("cors_allowed_origins") or []),
        "auth_token_configured": bool(str(admin_api.get("auth_token", "")).strip()),
    }



def resolve_target_feishu_webhook(config: Dict[str, Any], target: Dict[str, Any]) -> str:
    webhooks = resolve_target_feishu_webhooks(config, target)
    return webhooks[0] if webhooks else ""


def resolve_target_feishu_webhooks(config: Dict[str, Any], target: Dict[str, Any]) -> List[str]:
    notify = ensure_notify(config)
    group_lookup = {group["key"]: group for group in list_notify_groups(config, include_secret=True)}
    resolved: List[str] = []
    seen = set()
    for desired_group in target_group_keys(target, config):
        group = group_lookup.get(desired_group)
        webhook = str((group or {}).get("webhook") or "").strip()
        if webhook and webhook not in seen:
            resolved.append(webhook)
            seen.add(webhook)
    if resolved:
        return resolved
    legacy = str(notify.get("feishu_webhook", "")).strip()
    if legacy:
        return [legacy]
    default_group = next((group for group in group_lookup.values() if bool(group.get("is_default"))), None)
    if default_group and str(default_group.get("webhook", "")).strip():
        return [str(default_group.get("webhook", "")).strip()]
    return []
