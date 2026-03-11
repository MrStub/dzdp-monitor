#!/usr/bin/env python3
import copy
import json
import os
import re
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
            "session_ttl_hours": 168,
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
    admin_api.setdefault("session_ttl_hours", 168)
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
    return normalize_url(str(target.get("url", "")))



def target_group_key(target: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> str:
    raw = str(target.get("group_key") or target.get("notify_group_key") or "").strip()
    if raw:
        raw = slugify_key(raw) or raw
    if raw:
        return raw
    if config is not None:
        return str(ensure_notify(config).get("default_group_key", DEFAULT_GROUP_KEY))
    return DEFAULT_GROUP_KEY



def normalize_targets_in_place(config: Dict[str, Any]) -> bool:
    targets = ensure_targets(config)
    valid_group_keys = set(get_group_keys(config))
    default_group = str(ensure_notify(config).get("default_group_key", DEFAULT_GROUP_KEY))
    changed = False
    for target in targets:
        normalized_name = target_name(target)
        normalized_url = target_url(target)
        normalized_activity_id = parse_activity_id(normalized_url, target.get("activity_id"))
        normalized_group_key = target_group_key(target, config)
        if normalized_group_key not in valid_group_keys:
            normalized_group_key = default_group

        if target.get("name") != normalized_name:
            target["name"] = normalized_name
            changed = True
        if target.get("url") != normalized_url:
            target["url"] = normalized_url
            changed = True
        if normalized_activity_id and str(target.get("activity_id", "")).strip() != normalized_activity_id:
            target["activity_id"] = normalized_activity_id
            changed = True
        if target.get("group_key") != normalized_group_key:
            target["group_key"] = normalized_group_key
            changed = True
        if "notify_group_key" in target and target.get("notify_group_key") != normalized_group_key:
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
    after = json.dumps(config, ensure_ascii=False, sort_keys=True)
    return before != after



def list_targets(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    normalize_config_in_place(config)
    rows = []
    for idx, target in enumerate(ensure_targets(config), start=1):
        rows.append(
            {
                "index": idx,
                "activity_id": target_activity_id(target),
                "name": target_name(target),
                "url": target_url(target),
                "group_key": target_group_key(target, config),
            }
        )
    return rows



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
    return [idx for idx, target in enumerate(targets) if target_url(target) == wanted]



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
    groups = ensure_feishu_groups(config)
    valid_keys = {group["key"] for group in groups}
    fallback_key = str(ensure_notify(config).get("default_group_key", DEFAULT_GROUP_KEY))
    normalized = slugify_key(group_key_value or "") or fallback_key
    if normalized not in valid_keys:
        raise ConfigError(f"Unknown notify group: {group_key_value}")
    return normalized



def add_target(
    config: Dict[str, Any],
    *,
    url: str,
    name: Optional[str],
    activity_id: Optional[str],
    group_key_value: Optional[str],
    upsert: bool,
) -> Dict[str, Any]:
    normalize_config_in_place(config)
    targets = ensure_targets(config)
    normalized_url = normalize_url(url)
    aid = parse_activity_id(normalized_url, activity_id)
    if not aid:
        raise ConfigError("Cannot parse activity_id from url. Please pass activity_id explicitly.")
    final_name = str(name or f"target-{aid}").strip()
    if not final_name:
        raise ConfigError("Target name cannot be empty.")
    final_group_key = ensure_group_exists(config, group_key_value)
    idx = find_target_index(targets, aid)
    ensure_target_name_unique(targets, final_name, current_index=idx if idx >= 0 else None)
    new_obj = {
        "name": final_name,
        "url": normalized_url,
        "activity_id": aid,
        "group_key": final_group_key,
    }
    if idx >= 0:
        if not upsert:
            raise ConfigError(f"Target already exists: activity_id={aid}")
        targets[idx] = new_obj
        action = "updated"
    else:
        targets.append(new_obj)
        action = "added"
    return {"action": action, "target": new_obj, "total": len(targets)}



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
    set_group_key: Optional[str],
) -> Dict[str, Any]:
    normalize_config_in_place(config)
    targets = ensure_targets(config)
    idx, err = resolve_target_index(
        targets,
        activity_id=activity_id,
        index=index,
        name=selector_name,
        url=selector_url,
    )
    if idx < 0:
        raise ConfigError(err or "Target not found")
    if set_name is None and set_url is None and new_activity_id is None and set_group_key is None:
        raise ConfigError("No update fields provided.")

    cur = dict(targets[idx])
    current_activity_id = target_activity_id(cur) or ""
    final_url = normalize_url(set_url) if set_url is not None else target_url(cur)
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
    if set_group_key is not None:
        cur["group_key"] = ensure_group_exists(config, set_group_key)
    cur["activity_id"] = final_activity_id
    targets[idx] = cur
    return {
        "action": "updated",
        "old_activity_id": current_activity_id,
        "target": {
            "index": idx + 1,
            "activity_id": target_activity_id(cur),
            "name": target_name(cur),
            "url": target_url(cur),
            "group_key": target_group_key(cur, config),
        },
    }



def remove_target(
    config: Dict[str, Any],
    *,
    activity_id: Optional[str],
    index: Optional[int],
    name: Optional[str],
    url: Optional[str],
) -> Dict[str, Any]:
    normalize_config_in_place(config)
    targets = ensure_targets(config)
    idx, err = resolve_target_index(
        targets,
        activity_id=activity_id,
        index=index,
        name=name,
        url=url,
    )
    if idx < 0:
        raise ConfigError(err or "Target not found")
    removed = targets.pop(idx)
    return {
        "action": "removed",
        "target": {
            "index": idx + 1,
            "activity_id": target_activity_id(removed),
            "name": target_name(removed),
            "url": target_url(removed),
            "group_key": target_group_key(removed, config),
        },
        "total": len(targets),
    }



def find_group_index(groups: List[Dict[str, Any]], key_value: str) -> int:
    wanted = slugify_key(key_value) or str(key_value or "").strip()
    for idx, group in enumerate(groups):
        if group_key(group) == wanted:
            return idx
    return -1



def list_notify_groups(config: Dict[str, Any], include_secret: bool = False) -> List[Dict[str, Any]]:
    normalize_config_in_place(config)
    groups = ensure_feishu_groups(config)
    default_group_key = str(ensure_notify(config).get("default_group_key", DEFAULT_GROUP_KEY))
    rows = []
    for group in groups:
        webhook = group_webhook(group)
        rows.append(
            {
                "key": group_key(group),
                "name": group_name(group),
                "is_default": group_key(group) == default_group_key,
                "webhook": webhook if include_secret else "",
                "webhook_masked": mask_secret(webhook),
                "webhook_configured": bool(webhook),
            }
        )
    return rows



def add_notify_group(config: Dict[str, Any], *, key_value: Optional[str], name: str, webhook: str) -> Dict[str, Any]:
    normalize_config_in_place(config)
    groups = ensure_feishu_groups(config)
    final_name = str(name or "").strip()
    if not final_name:
        raise ConfigError("Group name cannot be empty.")
    base_key = slugify_key(key_value or final_name)
    if not base_key:
        base_key = f"group-{len(groups) + 1}"
    final_key = base_key
    suffix = 2
    while find_group_index(groups, final_key) >= 0:
        final_key = f"{base_key}-{suffix}"
        suffix += 1
    group = {"key": final_key, "name": final_name, "webhook": str(webhook or "").strip()}
    groups.append(group)
    return {
        "action": "added",
        "group": {
            "key": final_key,
            "name": final_name,
            "webhook_masked": mask_secret(group["webhook"]),
            "webhook_configured": bool(group["webhook"]),
            "is_default": False,
        },
        "total": len(groups),
    }



def update_notify_group(
    config: Dict[str, Any],
    *,
    key_value: str,
    set_name: Optional[str],
    set_webhook: Optional[str],
    make_default: Optional[bool],
) -> Dict[str, Any]:
    normalize_config_in_place(config)
    groups = ensure_feishu_groups(config)
    notify = ensure_notify(config)
    idx = find_group_index(groups, key_value)
    if idx < 0:
        raise ConfigError(f"Notify group not found: key={key_value}")
    if set_name is None and set_webhook is None and make_default is None:
        raise ConfigError("No update fields provided.")
    group = dict(groups[idx])
    if set_name is not None:
        final_name = str(set_name).strip()
        if not final_name:
            raise ConfigError("Group name cannot be empty.")
        group["name"] = final_name
    if set_webhook is not None:
        group["webhook"] = str(set_webhook or "").strip()
    groups[idx] = group
    if make_default:
        notify["default_group_key"] = group["key"]
    return {
        "action": "updated",
        "group": {
            "key": group["key"],
            "name": group["name"],
            "webhook_masked": mask_secret(group.get("webhook", "")),
            "webhook_configured": bool(group.get("webhook", "")),
            "is_default": group["key"] == notify.get("default_group_key"),
        },
    }



def remove_notify_group(config: Dict[str, Any], *, key_value: str) -> Dict[str, Any]:
    normalize_config_in_place(config)
    groups = ensure_feishu_groups(config)
    notify = ensure_notify(config)
    idx = find_group_index(groups, key_value)
    if idx < 0:
        raise ConfigError(f"Notify group not found: key={key_value}")
    if len(groups) == 1:
        raise ConfigError("Cannot remove the last notify group.")
    removed = groups.pop(idx)
    default_group_key = str(notify.get("default_group_key", DEFAULT_GROUP_KEY))
    if removed["key"] == default_group_key:
        notify["default_group_key"] = groups[0]["key"]
    reassigned_group_key = str(notify.get("default_group_key", groups[0]["key"]))
    for target in ensure_targets(config):
        if target_group_key(target, config) == removed["key"]:
            target["group_key"] = reassigned_group_key
    return {
        "action": "removed",
        "group": {
            "key": removed["key"],
            "name": removed["name"],
        },
        "reassigned_group_key": reassigned_group_key,
        "total": len(groups),
    }



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
    notify = ensure_notify(config)
    group_lookup = {group["key"]: group for group in ensure_feishu_groups(config)}
    desired_group = target_group_key(target, config)
    group = group_lookup.get(desired_group)
    if group and group_webhook(group):
        return group_webhook(group)
    legacy = str(notify.get("feishu_webhook", "")).strip()
    if legacy:
        return legacy
    default_group = group_lookup.get(str(notify.get("default_group_key", DEFAULT_GROUP_KEY)))
    if default_group:
        return group_webhook(default_group)
    return ""
