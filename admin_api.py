#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from app_config import (
    ConfigError,
    add_notify_group,
    add_target,
    get_admin_api_config_for_api,
    get_interval_seconds,
    get_proxy_config_for_api,
    list_notify_groups,
    list_targets,
    load_config,
    normalize_config_in_place,
    remove_notify_group,
    remove_target,
    save_config,
    update_notify_group,
    update_proxy_config,
    update_target,
)


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class DzdpAdminServer(ThreadingHTTPServer):
    def __init__(self, server_address: Tuple[str, int], handler_cls, config_path: str):
        super().__init__(server_address, handler_cls)
        self.config_path = config_path


class AdminApiHandler(BaseHTTPRequestHandler):
    server: DzdpAdminServer

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._handle_options()

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch("PATCH")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def log_message(self, fmt: str, *args: Any) -> None:
        logging.info("admin-api %s - %s", self.address_string(), fmt % args)

    def _dispatch(self, method: str) -> None:
        try:
            config, normalized_changed = self._load_config()
            origin = self._resolve_cors_origin(config)
            if method == "OPTIONS":
                self._write_json(HTTPStatus.NO_CONTENT, {}, origin, config)
                return
            self._ensure_authorized(config)

            path = urlparse(self.path).path.rstrip("/") or "/"
            parts = [segment for segment in path.split("/") if segment]
            if len(parts) < 2 or parts[0] != "api":
                raise ApiError(HTTPStatus.NOT_FOUND, f"Unsupported path: {path}")

            response_payload = self._route_request(method, parts[1:], config)
            if normalized_changed:
                save_config(self.server.config_path, config)
            self._write_json(HTTPStatus.OK, response_payload, origin, config)
        except ApiError as exc:
            config = self._safe_load_config()
            origin = self._resolve_cors_origin(config) if config else None
            self._write_json(exc.status, {"error": exc.message}, origin, config)
        except ConfigError as exc:
            config = self._safe_load_config()
            origin = self._resolve_cors_origin(config) if config else None
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)}, origin, config)
        except Exception as exc:  # noqa: BLE001
            logging.exception("Unhandled admin API error")
            config = self._safe_load_config()
            origin = self._resolve_cors_origin(config) if config else None
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)}, origin, config)

    def _handle_options(self) -> None:
        config = self._safe_load_config()
        origin = self._resolve_cors_origin(config) if config else None
        self._write_json(HTTPStatus.NO_CONTENT, {}, origin, config)

    def _safe_load_config(self) -> Optional[Dict[str, Any]]:
        try:
            config = load_config(self.server.config_path)
            normalize_config_in_place(config)
            return config
        except Exception:  # noqa: BLE001
            return None

    def _load_config(self) -> Tuple[Dict[str, Any], bool]:
        if not os.path.exists(self.server.config_path):
            raise ApiError(HTTPStatus.NOT_FOUND, f"config not found: {self.server.config_path}")
        config = load_config(self.server.config_path)
        changed = normalize_config_in_place(config)
        return config, changed

    def _resolve_cors_origin(self, config: Optional[Dict[str, Any]]) -> Optional[str]:
        if not config:
            return "*"
        admin_api = config.get("admin_api", {}) or {}
        allowed = admin_api.get("cors_allowed_origins", ["*"]) or ["*"]
        request_origin = self.headers.get("Origin", "")
        if "*" in allowed:
            return "*"
        if request_origin and request_origin in allowed:
            return request_origin
        return allowed[0] if allowed else None

    def _ensure_authorized(self, config: Dict[str, Any]) -> None:
        admin_api = config.get("admin_api", {}) or {}
        auth_token = str(admin_api.get("auth_token", "")).strip()
        if not auth_token:
            return
        header = str(self.headers.get("Authorization", "")).strip()
        if header == f"Bearer {auth_token}":
            return
        raise ApiError(HTTPStatus.UNAUTHORIZED, "Unauthorized")

    def _route_request(self, method: str, parts: List[str], config: Dict[str, Any]) -> Dict[str, Any]:
        resource = parts[0]
        if resource == "health" and method == "GET":
            return {"ok": True, "time": self._now_iso()}
        if resource == "dashboard" and method == "GET":
            return self._build_dashboard(config)
        if resource == "targets":
            return self._handle_targets(method, parts[1:], config)
        if resource == "notify-groups":
            return self._handle_notify_groups(method, parts[1:], config)
        if resource == "poll":
            return self._handle_poll(method, config)
        if resource == "proxy":
            return self._handle_proxy(method, config)
        raise ApiError(HTTPStatus.NOT_FOUND, f"Unsupported resource: {resource}")

    def _handle_targets(self, method: str, parts: List[str], config: Dict[str, Any]) -> Dict[str, Any]:
        if method == "GET" and not parts:
            return {"items": self._build_target_views(config), "summary": self._build_summary(config)}
        if method == "POST" and not parts:
            payload = self._read_json_body()
            result = add_target(
                config,
                url=str(payload.get("url") or "").strip(),
                name=payload.get("name"),
                activity_id=payload.get("activity_id"),
                group_key_value=payload.get("group_key"),
                upsert=bool(payload.get("upsert", False)),
            )
            save_config(self.server.config_path, config)
            return result
        if not parts:
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Unsupported targets method")

        index = self._parse_index(parts[0])
        if method == "PATCH":
            payload = self._read_json_body()
            result = update_target(
                config,
                activity_id=None,
                index=index,
                selector_name=None,
                selector_url=None,
                set_name=payload.get("set_name"),
                set_url=payload.get("set_url"),
                new_activity_id=payload.get("new_activity_id"),
                set_group_key=payload.get("set_group_key"),
            )
            save_config(self.server.config_path, config)
            return result
        if method == "DELETE":
            result = remove_target(
                config,
                activity_id=None,
                index=index,
                name=None,
                url=None,
            )
            save_config(self.server.config_path, config)
            return result
        raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Unsupported targets method")

    def _handle_notify_groups(self, method: str, parts: List[str], config: Dict[str, Any]) -> Dict[str, Any]:
        if method == "GET" and not parts:
            return {"items": list_notify_groups(config)}
        if method == "POST" and not parts:
            payload = self._read_json_body()
            result = add_notify_group(
                config,
                key_value=payload.get("key"),
                name=str(payload.get("name") or "").strip(),
                webhook=str(payload.get("webhook") or "").strip(),
            )
            save_config(self.server.config_path, config)
            return result
        if not parts:
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Unsupported notify-groups method")

        key_value = unquote(parts[0])
        if method == "PATCH":
            payload = self._read_json_body()
            result = update_notify_group(
                config,
                key_value=key_value,
                set_name=payload.get("set_name"),
                set_webhook=payload.get("set_webhook"),
                make_default=True if payload.get("make_default") else None,
            )
            save_config(self.server.config_path, config)
            return result
        if method == "DELETE":
            result = remove_notify_group(config, key_value=key_value)
            save_config(self.server.config_path, config)
            return result
        raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Unsupported notify-groups method")

    def _handle_poll(self, method: str, config: Dict[str, Any]) -> Dict[str, Any]:
        if method == "GET":
            return {"interval_seconds": get_interval_seconds(config)}
        if method == "PUT":
            payload = self._read_json_body()
            seconds = int(payload.get("seconds") or 0)
            if seconds < 5:
                raise ApiError(HTTPStatus.BAD_REQUEST, "seconds must be >= 5")
            config.setdefault("poll", {})["interval_seconds"] = seconds
            save_config(self.server.config_path, config)
            return {"action": "updated", "interval_seconds": seconds}
        raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Unsupported poll method")

    def _handle_proxy(self, method: str, config: Dict[str, Any]) -> Dict[str, Any]:
        if method == "GET":
            return get_proxy_config_for_api(config)
        if method == "PUT":
            payload = self._read_json_body()
            result = update_proxy_config(config, payload)
            save_config(self.server.config_path, config)
            return result
        raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Unsupported proxy method")

    def _build_dashboard(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "generated_at": self._now_iso(),
            "summary": self._build_summary(config),
            "targets": self._build_target_views(config),
            "notify_groups": list_notify_groups(config),
            "poll": {"interval_seconds": get_interval_seconds(config)},
            "proxy": get_proxy_config_for_api(config),
            "admin_api": get_admin_api_config_for_api(config),
        }

    def _build_summary(self, config: Dict[str, Any]) -> Dict[str, Any]:
        target_views = self._build_target_views(config)
        summary = {
            "total_targets": len(target_views),
            "in_stock": 0,
            "sold_out": 0,
            "unknown": 0,
            "error_targets": 0,
        }
        for item in target_views:
            state = str(item.get("last_state") or "UNKNOWN")
            if state == "IN_STOCK":
                summary["in_stock"] += 1
            elif state == "SOLD_OUT":
                summary["sold_out"] += 1
            else:
                summary["unknown"] += 1
            if item.get("last_error_text"):
                summary["error_targets"] += 1
        return summary

    def _build_target_views(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        targets = list_targets(config)
        states = self._load_state_snapshot(config.get("sqlite_path", "data/monitor_state.db"))
        group_lookup = {row["key"]: row["name"] for row in list_notify_groups(config)}
        enriched: List[Dict[str, Any]] = []
        for row in targets:
            state = states.get(str(row.get("activity_id") or ""), {})
            enriched.append(
                {
                    **row,
                    "group_name": group_lookup.get(row.get("group_key"), row.get("group_key")),
                    "last_state": state.get("last_state") or "UNKNOWN",
                    "last_sold_out": state.get("last_sold_out"),
                    "last_title": state.get("last_title") or "",
                    "last_change_ts": state.get("last_change_ts") or "",
                    "last_error_text": state.get("last_error_text") or "",
                    "last_error_streak": int(state.get("last_error_streak") or 0),
                    "fail_count": int(state.get("fail_count") or 0),
                }
            )
        return enriched

    def _load_state_snapshot(self, db_path: str) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(db_path):
            return {}
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT activity_id, last_state, last_sold_out, last_title, last_change_ts,
                       last_error_text, last_error_streak, fail_count
                FROM target_state
                """
            ).fetchall()
            return {str(row["activity_id"]): dict(row) for row in rows}
        finally:
            conn.close()

    def _parse_index(self, raw_value: str) -> int:
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"Invalid index: {raw_value}") from exc
        if value <= 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"Invalid index: {raw_value}")
        return value

    def _read_json_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"Invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "JSON body must be an object")
        return data

    def _write_json(
        self,
        status: int,
        payload: Dict[str, Any],
        origin: Optional[str],
        config: Optional[Dict[str, Any]],
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            if origin != "*":
                self.send_header("Vary", "Origin")
        self.end_headers()
        if status != HTTPStatus.NO_CONTENT:
            self.wfile.write(body)

    def _now_iso(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description="dzdp monitor admin API")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"配置文件不存在: {args.config}")
        return 1

    config = load_config(args.config)
    normalize_config_in_place(config)
    log_level = str(config.get("log_level", "INFO")).upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format="%(asctime)s | %(levelname)s | %(message)s")

    admin_api = config.get("admin_api", {}) or {}
    host = str(admin_api.get("listen_host", "0.0.0.0") or "0.0.0.0")
    port = int(admin_api.get("listen_port", 8787) or 8787)

    httpd = DzdpAdminServer((host, port), AdminApiHandler, os.path.abspath(args.config))
    logging.info("Admin API listening on %s:%s using config %s", host, port, os.path.abspath(args.config))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("Admin API stopped by user")
        return 0
    finally:
        httpd.server_close()


if __name__ == "__main__":
    sys.exit(main())
