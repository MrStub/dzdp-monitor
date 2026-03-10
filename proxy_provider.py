#!/usr/bin/env python3
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests

from app_config import ensure_proxy


class ProxyResolutionError(RuntimeError):
    pass


class ProxyResolver:
    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get_requests_proxies(
        self,
        config: Dict[str, Any],
        *,
        target_key: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        proxy_cfg = ensure_proxy(config)
        if not bool(proxy_cfg.get("enabled", False)):
            return None

        api_url = str(proxy_cfg.get("api_url", "")).strip()
        if not api_url:
            raise ProxyResolutionError("proxy enabled but api_url is empty")

        sticky_mode = str(proxy_cfg.get("sticky_mode", "shared")).strip().lower()
        cache_seconds = max(1, int(proxy_cfg.get("cache_seconds", 120) or 120))
        cache_key = target_key if sticky_mode == "per_target" and target_key else "__shared__"
        now_ts = time.time()
        cached = self._cache.get(cache_key)
        if cached and float(cached.get("expires_at", 0)) > now_ts:
            return dict(cached["proxies"])

        proxies = self._fetch_proxy(proxy_cfg)
        self._cache[cache_key] = {
            "proxies": dict(proxies),
            "expires_at": now_ts + cache_seconds,
        }
        return dict(proxies)

    def _fetch_proxy(self, proxy_cfg: Dict[str, Any]) -> Dict[str, str]:
        method = str(proxy_cfg.get("request_method", "GET") or "GET").strip().upper()
        headers = dict(proxy_cfg.get("extra_headers") or {})
        api_key = str(proxy_cfg.get("api_key", "") or "").strip()
        api_key_header = str(proxy_cfg.get("api_key_header", "X-API-Key") or "X-API-Key").strip()
        if api_key and api_key_header:
            headers[api_key_header] = api_key

        request_kwargs: Dict[str, Any] = {
            "method": method,
            "url": str(proxy_cfg.get("api_url", "")).strip(),
            "headers": headers,
            "params": dict(proxy_cfg.get("query_params") or {}),
            "timeout": max(1, int(proxy_cfg.get("timeout_seconds", 8) or 8)),
            "verify": bool(proxy_cfg.get("verify_ssl", True)),
        }
        if method != "GET":
            request_kwargs["json"] = dict(proxy_cfg.get("request_body") or {})

        try:
            resp = requests.request(**request_kwargs)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ProxyResolutionError(f"proxy provider request failed: {exc}") from exc

        proxy_item = self._extract_proxy_item(payload, str(proxy_cfg.get("response_data_path", "")))
        if not isinstance(proxy_item, dict):
            raise ProxyResolutionError("proxy provider response is not an object")

        response_fields = dict(proxy_cfg.get("response_fields") or {})
        proxy_url = self._read_path(proxy_item, str(response_fields.get("proxy_url", "proxy_url")))
        if proxy_url:
            final_proxy_url = str(proxy_url).strip()
        else:
            scheme = str(self._read_path(proxy_item, str(response_fields.get("scheme", "scheme"))) or "http").strip()
            host = str(self._read_path(proxy_item, str(response_fields.get("host", "host"))) or "").strip()
            port = str(self._read_path(proxy_item, str(response_fields.get("port", "port"))) or "").strip()
            username = str(self._read_path(proxy_item, str(response_fields.get("username", "username"))) or "").strip()
            password = str(self._read_path(proxy_item, str(response_fields.get("password", "password"))) or "").strip()
            if not host or not port:
                raise ProxyResolutionError("proxy provider response missing host/port")
            auth = ""
            if username:
                auth = quote(username, safe="")
                if password:
                    auth += f":{quote(password, safe='')}"
                auth += "@"
            final_proxy_url = f"{scheme}://{auth}{host}:{port}"

        logging.debug("Resolved proxy from provider: %s", self._mask_proxy(final_proxy_url))
        return {"http": final_proxy_url, "https": final_proxy_url}

    def _extract_proxy_item(self, payload: Any, data_path: str) -> Any:
        current = payload
        if data_path:
            current = self._read_path(payload, data_path)
        elif isinstance(payload, dict) and "data" in payload:
            current = payload.get("data")
        if isinstance(current, list):
            if not current:
                raise ProxyResolutionError("proxy provider returned an empty list")
            current = current[0]
        return current

    def _read_path(self, payload: Any, path: str) -> Any:
        current = payload
        for segment in [part for part in str(path or "").split(".") if part]:
            if isinstance(current, list):
                try:
                    current = current[int(segment)]
                except (ValueError, IndexError):
                    return None
                continue
            if not isinstance(current, dict):
                return None
            current = current.get(segment)
            if current is None:
                return None
        return current

    def _mask_proxy(self, proxy_url: str) -> str:
        if "@" not in proxy_url:
            return proxy_url
        prefix, suffix = proxy_url.split("@", 1)
        if "://" not in prefix:
            return proxy_url
        scheme, _ = prefix.split("://", 1)
        return f"{scheme}://***@{suffix}"
