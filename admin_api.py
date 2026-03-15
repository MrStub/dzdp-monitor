#!/usr/bin/env python3
import argparse
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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

PERMISSION_KEYS = (
    "targets_read",
    "targets_create",
    "targets_update",
    "targets_delete",
    "webhook_manage",
    "poll_manage",
    "proxy_manage",
)
ALL_PERMISSIONS = {key: True for key in PERMISSION_KEYS}
DEFAULT_OPERATOR_PERMISSIONS = {
    "targets_read": True,
    "targets_create": True,
    "targets_update": False,
    "targets_delete": False,
    "webhook_manage": False,
    "poll_manage": False,
    "proxy_manage": False,
}
PASSWORD_PBKDF2_ITERATIONS = 260_000
DEFAULT_MAX_JSON_BODY_BYTES = 1_048_576
DEFAULT_LOGIN_FAIL_THRESHOLD = 5
DEFAULT_LOGIN_FAIL_WINDOW_SECONDS = 600
DEFAULT_LOGIN_BLOCK_SECONDS = 600


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class AuthContext:
    user_id: Optional[int]
    username: str
    is_admin: bool
    permissions: Dict[str, bool]
    is_legacy_token: bool = False

    def can(self, permission: str) -> bool:
        return self.is_admin or bool(self.permissions.get(permission))


class DzdpAdminServer(ThreadingHTTPServer):
    def __init__(self, server_address: Tuple[str, int], handler_cls, config_path: str):
        super().__init__(server_address, handler_cls)
        self.config_path = config_path
        self.login_rate_limiter = LoginRateLimiter()


class LoginRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Dict[str, Any]] = {}

    def _key(self, ip: str, username: str) -> str:
        return f"{str(ip or '').strip()}|{str(username or '').strip().lower()}"

    def _cleanup_locked(self, now: float, window_seconds: int) -> None:
        to_delete: List[str] = []
        for key, entry in self._state.items():
            fails = [ts for ts in entry.get("fails", []) if now - float(ts) <= window_seconds]
            entry["fails"] = fails
            blocked_until = float(entry.get("blocked_until", 0.0) or 0.0)
            if blocked_until <= now and not fails:
                to_delete.append(key)
        for key in to_delete:
            self._state.pop(key, None)

    def check_blocked(self, ip: str, username: str, *, window_seconds: int) -> int:
        now = time.time()
        key = self._key(ip, username)
        with self._lock:
            self._cleanup_locked(now, max(1, int(window_seconds)))
            entry = self._state.get(key)
            if not entry:
                return 0
            blocked_until = float(entry.get("blocked_until", 0.0) or 0.0)
            if blocked_until <= now:
                return 0
            return max(1, int(blocked_until - now))

    def record_failure(
        self,
        ip: str,
        username: str,
        *,
        threshold: int,
        window_seconds: int,
        block_seconds: int,
    ) -> int:
        now = time.time()
        key = self._key(ip, username)
        threshold = max(1, int(threshold))
        window_seconds = max(1, int(window_seconds))
        block_seconds = max(1, int(block_seconds))
        with self._lock:
            self._cleanup_locked(now, window_seconds)
            entry = self._state.setdefault(key, {"fails": [], "blocked_until": 0.0})
            fails = [ts for ts in entry.get("fails", []) if now - float(ts) <= window_seconds]
            fails.append(now)
            entry["fails"] = fails
            if len(fails) >= threshold:
                blocked_until = now + block_seconds
                entry["blocked_until"] = blocked_until
                entry["fails"] = []
                return max(1, int(blocked_until - now))
            return 0

    def record_success(self, ip: str, username: str) -> None:
        key = self._key(ip, username)
        with self._lock:
            self._state.pop(key, None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _to_iso(value: datetime) -> str:
    return value.astimezone().isoformat(timespec="seconds")


def _password_hash(password: str, salt_bytes: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        PASSWORD_PBKDF2_ITERATIONS,
    )
    return base64.b64encode(digest).decode("ascii")


def _new_password_material(password: str) -> Tuple[str, str]:
    salt_bytes = secrets.token_bytes(16)
    return base64.b64encode(salt_bytes).decode("ascii"), _password_hash(password, salt_bytes)


def _verify_password(password: str, salt_b64: str, expected_hash_b64: str) -> bool:
    try:
        salt_bytes = base64.b64decode(salt_b64.encode("ascii"))
    except Exception:  # noqa: BLE001
        return False
    actual = _password_hash(password, salt_bytes)
    return hmac.compare_digest(actual, expected_hash_b64)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthStore:
    def __init__(
        self,
        db_path: str,
        *,
        session_ttl_hours: int,
        default_admin_username: str,
        default_admin_password: str,
        legacy_auth_token: str,
    ):
        self.db_path = db_path
        self.session_ttl_hours = max(1, int(session_ttl_hours or 1440))
        self.default_admin_username = str(default_admin_username or "admin").strip() or "admin"
        self.default_admin_password = str(default_admin_password or "").strip()
        self.legacy_auth_token = str(legacy_auth_token or "").strip()

    def _connect(self) -> sqlite3.Connection:
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def ensure_schema_and_admin(self) -> None:
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            self._ensure_default_admin(conn)
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_permissions (
                user_id INTEGER NOT NULL,
                permission TEXT NOT NULL,
                allowed INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, permission),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                last_seen_at TEXT,
                ip TEXT,
                user_agent TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id INTEGER,
                actor_username TEXT NOT NULL,
                action TEXT NOT NULL,
                resource TEXT NOT NULL,
                resource_id TEXT,
                detail_json TEXT,
                created_at TEXT NOT NULL,
                ip TEXT
            )
            """
        )

    def _ensure_default_admin(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ? LIMIT 1",
            (self.default_admin_username,),
        ).fetchone()
        if row:
            return
        admin_password = self.default_admin_password or secrets.token_urlsafe(16)
        if not self.default_admin_password:
            output_path = self._write_bootstrap_password_file(self.default_admin_username, admin_password)
            logging.warning("admin_api.default_admin_password 未配置。已将一次性默认管理员密码写入本地受限文件: %s", output_path)
            logging.warning("请尽快在配置文件中设置 admin_api.default_admin_password，并在首次登录后修改密码。")
        salt_b64, hash_b64 = _new_password_material(admin_password)
        now = _to_iso(_utcnow())
        cursor = conn.execute(
            """
            INSERT INTO users (username, password_hash, password_salt, is_admin, is_active, created_at, updated_at)
            VALUES (?, ?, ?, 1, 1, ?, ?)
            """,
            (self.default_admin_username, hash_b64, salt_b64, now, now),
        )
        self._upsert_permissions(
            conn,
            int(cursor.lastrowid),
            {key: True for key in PERMISSION_KEYS},
        )
        logging.info("已初始化默认管理员用户: %s", self.default_admin_username)

    def _write_bootstrap_password_file(self, username: str, password: str) -> str:
        db_dir = os.path.dirname(os.path.abspath(self.db_path)) or "."
        output_path = os.path.join(db_dir, "admin_bootstrap_credentials.txt")
        now = _to_iso(_utcnow())
        lines = [
            "# dzdp-monitor admin bootstrap credentials",
            f"generated_at={now}",
            f"username={username}",
            f"password={password}",
            "",
            "# This file contains sensitive data. Remove it after first successful login.",
            "",
        ]
        payload = "\n".join(lines).encode("utf-8")
        fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        try:
            os.chmod(output_path, 0o600)
        except OSError:
            logging.warning("无法设置管理员密码文件权限为 600: %s", output_path)
        return output_path

    def _build_permissions(self, conn: sqlite3.Connection, user_id: int, is_admin: bool) -> Dict[str, bool]:
        if is_admin:
            return dict(ALL_PERMISSIONS)
        values = {key: False for key in PERMISSION_KEYS}
        rows = conn.execute(
            "SELECT permission, allowed FROM user_permissions WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        for row in rows:
            key = str(row["permission"])
            if key in values:
                values[key] = bool(row["allowed"])
        return values

    def _build_context_from_user_row(self, conn: sqlite3.Connection, row: sqlite3.Row) -> AuthContext:
        user_id = int(row["id"])
        is_admin = bool(row["is_admin"])
        return AuthContext(
            user_id=user_id,
            username=str(row["username"]),
            is_admin=is_admin,
            permissions=self._build_permissions(conn, user_id, is_admin),
        )

    def login(self, username: str, password: str, *, ip: str, user_agent: str) -> Dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT id, username, password_hash, password_salt, is_admin, is_active
                FROM users
                WHERE username = ? LIMIT 1
                """,
                (username,),
            ).fetchone()
            if not row or not bool(row["is_active"]):
                raise ApiError(HTTPStatus.UNAUTHORIZED, "用户名或密码错误")
            if not _verify_password(password, str(row["password_salt"]), str(row["password_hash"])):
                raise ApiError(HTTPStatus.UNAUTHORIZED, "用户名或密码错误")

            token = secrets.token_urlsafe(36)
            now = _utcnow()
            now_iso = _to_iso(now)
            expires_at = now + timedelta(hours=self.session_ttl_hours)
            expires_iso = _to_iso(expires_at)
            conn.execute(
                """
                INSERT INTO auth_sessions (user_id, token_hash, created_at, expires_at, revoked_at, last_seen_at, ip, user_agent)
                VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (int(row["id"]), _token_hash(token), now_iso, expires_iso, now_iso, ip, user_agent),
            )
            conn.execute(
                "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                (now_iso, now_iso, int(row["id"])),
            )
            context = self._build_context_from_user_row(conn, row)
            conn.commit()
            return {
                "token": token,
                "token_type": "Bearer",
                "expires_at": expires_iso,
                "user": self._serialize_user(context),
                "permissions": context.permissions,
            }
        finally:
            conn.close()

    def resolve_context_from_bearer(self, bearer_token: str) -> Optional[AuthContext]:
        token = str(bearer_token or "").strip()
        if not token:
            return None
        conn = self._connect()
        try:
            token_row = conn.execute(
                """
                SELECT s.user_id, s.expires_at, s.revoked_at, u.id, u.username, u.is_admin, u.is_active
                FROM auth_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ?
                LIMIT 1
                """,
                (_token_hash(token),),
            ).fetchone()
            now = _utcnow()
            now_iso = _to_iso(now)
            if token_row and not token_row["revoked_at"] and bool(token_row["is_active"]):
                expires_at = datetime.fromisoformat(str(token_row["expires_at"]))
                if expires_at >= now:
                    conn.execute(
                        """
                        UPDATE auth_sessions
                        SET last_seen_at = ?
                        WHERE token_hash = ?
                        """,
                        (now_iso, _token_hash(token)),
                    )
                    conn.commit()
                    return self._build_context_from_user_row(conn, token_row)
            if self.legacy_auth_token and hmac.compare_digest(token, self.legacy_auth_token):
                return AuthContext(
                    user_id=None,
                    username="legacy-token-admin",
                    is_admin=True,
                    permissions=dict(ALL_PERMISSIONS),
                    is_legacy_token=True,
                )
            return None
        finally:
            conn.close()

    def logout(self, bearer_token: str) -> Dict[str, Any]:
        token = str(bearer_token or "").strip()
        if not token:
            return {"action": "no_token"}
        if self.legacy_auth_token and hmac.compare_digest(token, self.legacy_auth_token):
            return {"action": "legacy_token_noop"}
        conn = self._connect()
        try:
            now_iso = _to_iso(_utcnow())
            cursor = conn.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?, last_seen_at = ?
                WHERE token_hash = ? AND revoked_at IS NULL
                """,
                (now_iso, now_iso, _token_hash(token)),
            )
            conn.commit()
            if cursor.rowcount > 0:
                return {"action": "logged_out"}
            return {"action": "session_not_found"}
        finally:
            conn.close()

    def _serialize_user(self, context: AuthContext) -> Dict[str, Any]:
        return {
            "id": context.user_id,
            "username": context.username,
            "is_admin": context.is_admin,
        }

    def get_me(self, context: AuthContext) -> Dict[str, Any]:
        return {
            "user": self._serialize_user(context),
            "permissions": dict(context.permissions),
            "legacy_token": context.is_legacy_token,
        }

    def _upsert_permissions(self, conn: sqlite3.Connection, user_id: int, permissions: Dict[str, bool]) -> None:
        for key in PERMISSION_KEYS:
            allowed = 1 if permissions.get(key) else 0
            conn.execute(
                """
                INSERT INTO user_permissions (user_id, permission, allowed)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, permission) DO UPDATE SET allowed = excluded.allowed
                """,
                (user_id, key, allowed),
            )

    def list_users(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            self._ensure_default_admin(conn)
            rows = conn.execute(
                """
                SELECT id, username, is_admin, is_active, created_at, updated_at, last_login_at
                FROM users
                ORDER BY id ASC
                """
            ).fetchall()
            items: List[Dict[str, Any]] = []
            for row in rows:
                user_id = int(row["id"])
                is_admin = bool(row["is_admin"])
                items.append(
                    {
                        "id": user_id,
                        "username": str(row["username"]),
                        "is_admin": is_admin,
                        "is_active": bool(row["is_active"]),
                        "created_at": str(row["created_at"]),
                        "updated_at": str(row["updated_at"]),
                        "last_login_at": str(row["last_login_at"] or ""),
                        "permissions": self._build_permissions(conn, user_id, is_admin),
                    }
                )
            return items
        finally:
            conn.close()

    def create_user(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        username = str(payload.get("username") or "").strip()
        if not username:
            raise ApiError(HTTPStatus.BAD_REQUEST, "username 不能为空")
        if len(username) > 64:
            raise ApiError(HTTPStatus.BAD_REQUEST, "username 过长")
        requested_password = str(payload.get("password") or "").strip()
        is_admin = bool(payload.get("is_admin"))
        raw_permissions = payload.get("permissions")
        permissions = dict(DEFAULT_OPERATOR_PERMISSIONS)
        if is_admin:
            permissions = dict(ALL_PERMISSIONS)
        elif isinstance(raw_permissions, dict):
            permissions = {
                key: bool(raw_permissions.get(key, permissions[key])) for key in PERMISSION_KEYS
            }
        if not requested_password:
            requested_password = secrets.token_urlsafe(12)
        salt_b64, hash_b64 = _new_password_material(requested_password)
        now_iso = _to_iso(_utcnow())
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            self._ensure_default_admin(conn)
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO users (username, password_hash, password_salt, is_admin, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (username, hash_b64, salt_b64, 1 if is_admin else 0, now_iso, now_iso),
                )
            except sqlite3.IntegrityError as exc:
                raise ApiError(HTTPStatus.CONFLICT, f"用户已存在: {username}") from exc
            user_id = int(cursor.lastrowid)
            self._upsert_permissions(conn, user_id, permissions)
            conn.commit()
            return {
                "action": "created",
                "user": {
                    "id": user_id,
                    "username": username,
                    "is_admin": is_admin,
                    "permissions": permissions,
                },
                "generated_password": "" if str(payload.get("password") or "").strip() else requested_password,
            }
        finally:
            conn.close()

    def update_user_permissions(self, user_id: int, permissions: Dict[str, Any]) -> Dict[str, Any]:
        resolved = {key: bool(permissions.get(key, False)) for key in PERMISSION_KEYS}
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT id, username, is_admin FROM users WHERE id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
            if not row:
                raise ApiError(HTTPStatus.NOT_FOUND, f"用户不存在: {user_id}")
            now_iso = _to_iso(_utcnow())
            if bool(row["is_admin"]):
                conn.execute("UPDATE users SET updated_at = ? WHERE id = ?", (now_iso, user_id))
                conn.commit()
                return {
                    "action": "unchanged",
                    "user": {
                        "id": user_id,
                        "username": str(row["username"]),
                        "is_admin": True,
                        "permissions": dict(ALL_PERMISSIONS),
                    },
                }
            self._upsert_permissions(conn, user_id, resolved)
            conn.execute("UPDATE users SET updated_at = ? WHERE id = ?", (now_iso, user_id))
            conn.commit()
            return {
                "action": "updated",
                "user": {
                    "id": user_id,
                    "username": str(row["username"]),
                    "is_admin": False,
                    "permissions": resolved,
                },
            }
        finally:
            conn.close()

    def delete_user(self, user_id: int, actor_user_id: Optional[int]) -> Dict[str, Any]:
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT id, username, is_admin FROM users WHERE id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
            if not row:
                raise ApiError(HTTPStatus.NOT_FOUND, f"用户不存在: {user_id}")
            if actor_user_id is not None and user_id == actor_user_id:
                raise ApiError(HTTPStatus.BAD_REQUEST, "不能删除当前登录用户")
            if bool(row["is_admin"]):
                admin_count = conn.execute(
                    "SELECT COUNT(1) AS cnt FROM users WHERE is_admin = 1 AND is_active = 1"
                ).fetchone()
                if int(admin_count["cnt"]) <= 1:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "至少保留一个管理员账号")
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return {"action": "deleted", "user": {"id": user_id, "username": str(row["username"])}}
        finally:
            conn.close()

    def write_audit_log(
        self,
        *,
        actor: AuthContext,
        action: str,
        resource: str,
        resource_id: Optional[str],
        detail: Dict[str, Any],
        ip: str,
    ) -> None:
        conn = self._connect()
        try:
            self._ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO audit_logs (actor_user_id, actor_username, action, resource, resource_id, detail_json, created_at, ip)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    actor.user_id,
                    actor.username,
                    action,
                    resource,
                    resource_id or "",
                    json.dumps(detail, ensure_ascii=False),
                    _to_iso(_utcnow()),
                    ip,
                ),
            )
            conn.commit()
        finally:
            conn.close()


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
            auth_store = self._auth_store(config)
            auth_store.ensure_schema_and_admin()

            if method == "OPTIONS":
                self._write_json(HTTPStatus.NO_CONTENT, {}, origin, config)
                return

            path = urlparse(self.path).path.rstrip("/") or "/"
            parts = [segment for segment in path.split("/") if segment]
            if len(parts) < 2 or parts[0] != "api":
                raise ApiError(HTTPStatus.NOT_FOUND, f"Unsupported path: {path}")

            response_payload = self._route_request(method, parts[1:], config, auth_store)
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
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal server error"}, origin, config)

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
            return None
        admin_api = config.get("admin_api", {}) or {}
        raw_allowed = admin_api.get("cors_allowed_origins", []) or []
        allowed = [str(origin).strip() for origin in raw_allowed if str(origin).strip()]
        request_origin = self.headers.get("Origin", "")
        if "*" in allowed:
            return "*"
        if request_origin and request_origin in allowed:
            return request_origin
        return None

    def _auth_store(self, config: Dict[str, Any]) -> AuthStore:
        admin_api = config.get("admin_api", {}) or {}
        return AuthStore(
            db_path=str(config.get("sqlite_path") or "data/monitor_state.db"),
            session_ttl_hours=int(admin_api.get("session_ttl_hours", 1440) or 1440),
            default_admin_username=str(admin_api.get("default_admin_username", "admin")),
            default_admin_password=str(admin_api.get("default_admin_password", "")),
            legacy_auth_token=str(admin_api.get("auth_token", "")),
        )

    def _login_rate_limit_settings(self, config: Dict[str, Any]) -> Dict[str, int]:
        admin_api = config.get("admin_api", {}) or {}
        settings = admin_api.get("login_rate_limit")
        if not isinstance(settings, dict):
            settings = {}
        return {
            "threshold": max(1, int(settings.get("max_failures", DEFAULT_LOGIN_FAIL_THRESHOLD) or DEFAULT_LOGIN_FAIL_THRESHOLD)),
            "window_seconds": max(
                1,
                int(settings.get("window_seconds", DEFAULT_LOGIN_FAIL_WINDOW_SECONDS) or DEFAULT_LOGIN_FAIL_WINDOW_SECONDS),
            ),
            "block_seconds": max(1, int(settings.get("block_seconds", DEFAULT_LOGIN_BLOCK_SECONDS) or DEFAULT_LOGIN_BLOCK_SECONDS)),
        }

    def _max_body_bytes(self) -> int:
        config = self._safe_load_config()
        if not config:
            return DEFAULT_MAX_JSON_BODY_BYTES
        admin_api = config.get("admin_api", {}) or {}
        raw_value = admin_api.get("max_body_bytes", DEFAULT_MAX_JSON_BODY_BYTES)
        try:
            return max(1024, int(raw_value))
        except (TypeError, ValueError):
            return DEFAULT_MAX_JSON_BODY_BYTES

    def _parse_bearer(self) -> str:
        header = str(self.headers.get("Authorization", "")).strip()
        if not header:
            return ""
        if not header.lower().startswith("bearer "):
            return ""
        return header[7:].strip()

    def _require_auth(self, auth_store: AuthStore) -> AuthContext:
        token = self._parse_bearer()
        context = auth_store.resolve_context_from_bearer(token)
        if not context:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Unauthorized")
        return context

    def _require_admin(self, context: AuthContext) -> None:
        if not context.is_admin:
            raise ApiError(HTTPStatus.FORBIDDEN, "需要管理员权限")

    def _require_permission(self, context: AuthContext, permission: str) -> None:
        if not context.can(permission):
            raise ApiError(HTTPStatus.FORBIDDEN, f"缺少权限: {permission}")

    def _route_request(
        self,
        method: str,
        parts: List[str],
        config: Dict[str, Any],
        auth_store: AuthStore,
    ) -> Dict[str, Any]:
        resource = parts[0]
        if resource == "health" and method == "GET":
            return {"ok": True, "time": self._now_iso()}
        if resource == "auth":
            return self._handle_auth(method, parts[1:], auth_store, config)

        context = self._require_auth(auth_store)

        if resource == "dashboard" and method == "GET":
            return self._build_dashboard(config, context)
        if resource == "targets":
            return self._handle_targets(method, parts[1:], config, context, auth_store)
        if resource == "notify-groups":
            return self._handle_notify_groups(method, parts[1:], config, context, auth_store)
        if resource == "poll":
            return self._handle_poll(method, config, context, auth_store)
        if resource == "proxy":
            return self._handle_proxy(method, config, context, auth_store)
        if resource == "users":
            return self._handle_users(method, parts[1:], context, auth_store)
        raise ApiError(HTTPStatus.NOT_FOUND, f"Unsupported resource: {resource}")

    def _handle_auth(self, method: str, parts: List[str], auth_store: AuthStore, config: Dict[str, Any]) -> Dict[str, Any]:
        if method == "POST" and parts == ["login"]:
            payload = self._read_json_body()
            username = str(payload.get("username") or "").strip()
            password = str(payload.get("password") or "")
            if not username or not password:
                raise ApiError(HTTPStatus.BAD_REQUEST, "username 和 password 必填")
            client_ip = self._client_ip()
            limit_cfg = self._login_rate_limit_settings(config)
            retry_after = self.server.login_rate_limiter.check_blocked(
                client_ip,
                username,
                window_seconds=limit_cfg["window_seconds"],
            )
            if retry_after > 0:
                raise ApiError(HTTPStatus.TOO_MANY_REQUESTS, f"登录失败次数过多，请在 {retry_after} 秒后重试")
            try:
                result = auth_store.login(
                    username=username,
                    password=password,
                    ip=client_ip,
                    user_agent=str(self.headers.get("User-Agent", ""))[:512],
                )
            except ApiError as exc:
                if exc.status == HTTPStatus.UNAUTHORIZED:
                    retry_after = self.server.login_rate_limiter.record_failure(
                        client_ip,
                        username,
                        threshold=limit_cfg["threshold"],
                        window_seconds=limit_cfg["window_seconds"],
                        block_seconds=limit_cfg["block_seconds"],
                    )
                    if retry_after > 0:
                        logging.warning("登录限流触发: ip=%s username=%s retry_after=%ss", client_ip, username, retry_after)
                        raise ApiError(HTTPStatus.TOO_MANY_REQUESTS, f"登录失败次数过多，请在 {retry_after} 秒后重试") from exc
                raise
            self.server.login_rate_limiter.record_success(client_ip, username)
            return result
        if method == "POST" and parts == ["logout"]:
            context = self._require_auth(auth_store)
            result = auth_store.logout(self._parse_bearer())
            return {
                **result,
                "user": {"id": context.user_id, "username": context.username, "is_admin": context.is_admin},
            }
        if method == "GET" and parts == ["me"]:
            context = self._require_auth(auth_store)
            return auth_store.get_me(context)
        raise ApiError(HTTPStatus.NOT_FOUND, "Unsupported auth endpoint")

    def _handle_users(
        self,
        method: str,
        parts: List[str],
        context: AuthContext,
        auth_store: AuthStore,
    ) -> Dict[str, Any]:
        self._require_admin(context)
        if method == "GET" and not parts:
            return {"items": auth_store.list_users()}
        if method == "POST" and not parts:
            payload = self._read_json_body()
            result = auth_store.create_user(payload)
            auth_store.write_audit_log(
                actor=context,
                action="create",
                resource="users",
                resource_id=str(result.get("user", {}).get("id", "")),
                detail=result,
                ip=self._client_ip(),
            )
            return result
        if len(parts) == 2 and parts[1] == "permissions" and method == "PATCH":
            user_id = self._parse_index(parts[0])
            payload = self._read_json_body()
            raw_permissions = payload.get("permissions")
            if not isinstance(raw_permissions, dict):
                raise ApiError(HTTPStatus.BAD_REQUEST, "permissions 必须是对象")
            result = auth_store.update_user_permissions(user_id, raw_permissions)
            auth_store.write_audit_log(
                actor=context,
                action="update_permissions",
                resource="users",
                resource_id=str(user_id),
                detail={"permissions": raw_permissions, "result": result},
                ip=self._client_ip(),
            )
            return result
        if len(parts) == 1 and method == "DELETE":
            user_id = self._parse_index(parts[0])
            result = auth_store.delete_user(user_id, context.user_id)
            auth_store.write_audit_log(
                actor=context,
                action="delete",
                resource="users",
                resource_id=str(user_id),
                detail=result,
                ip=self._client_ip(),
            )
            return result
        raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Unsupported users method")

    def _handle_targets(
        self,
        method: str,
        parts: List[str],
        config: Dict[str, Any],
        context: AuthContext,
        auth_store: AuthStore,
    ) -> Dict[str, Any]:
        if method == "GET" and not parts:
            self._require_permission(context, "targets_read")
            return {"items": self._build_target_views(config), "summary": self._build_summary(config)}
        if method == "POST" and not parts:
            self._require_permission(context, "targets_create")
            payload = self._read_json_body()
            result = add_target(
                config,
                url=str(payload.get("url") or "").strip(),
                name=payload.get("name"),
                activity_id=payload.get("activity_id"),
                group_keys_values=payload.get("group_keys"),
                group_key_value=payload.get("group_key"),
                enabled=payload.get("enabled"),
                upsert=bool(payload.get("upsert", False)),
            )
            auth_store.write_audit_log(
                actor=context,
                action="create",
                resource="targets",
                resource_id=str(result.get("target", {}).get("activity_id", "")),
                detail=result,
                ip=self._client_ip(),
            )
            return result
        if not parts:
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Unsupported targets method")

        index = self._parse_index(parts[0])
        if method == "PATCH":
            self._require_permission(context, "targets_update")
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
                set_group_keys=payload.get("set_group_keys"),
                set_group_key=payload.get("set_group_key"),
                set_enabled=payload.get("set_enabled"),
            )
            auth_store.write_audit_log(
                actor=context,
                action="update",
                resource="targets",
                resource_id=str(index),
                detail={"payload": payload, "result": result},
                ip=self._client_ip(),
            )
            return result
        if method == "DELETE":
            self._require_permission(context, "targets_delete")
            result = remove_target(
                config,
                activity_id=None,
                index=index,
                name=None,
                url=None,
            )
            auth_store.write_audit_log(
                actor=context,
                action="delete",
                resource="targets",
                resource_id=str(index),
                detail=result,
                ip=self._client_ip(),
            )
            return result
        raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Unsupported targets method")

    def _handle_notify_groups(
        self,
        method: str,
        parts: List[str],
        config: Dict[str, Any],
        context: AuthContext,
        auth_store: AuthStore,
    ) -> Dict[str, Any]:
        self._require_permission(context, "webhook_manage")
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
            auth_store.write_audit_log(
                actor=context,
                action="create",
                resource="groups",
                resource_id=str(result.get("group", {}).get("key", "")),
                detail=result,
                ip=self._client_ip(),
            )
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
            auth_store.write_audit_log(
                actor=context,
                action="update",
                resource="groups",
                resource_id=key_value,
                detail={"payload": payload, "result": result},
                ip=self._client_ip(),
            )
            return result
        if method == "DELETE":
            result = remove_notify_group(config, key_value=key_value)
            auth_store.write_audit_log(
                actor=context,
                action="delete",
                resource="groups",
                resource_id=key_value,
                detail=result,
                ip=self._client_ip(),
            )
            return result
        raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Unsupported notify-groups method")

    def _handle_poll(
        self,
        method: str,
        config: Dict[str, Any],
        context: AuthContext,
        auth_store: AuthStore,
    ) -> Dict[str, Any]:
        self._require_permission(context, "poll_manage")
        if method == "GET":
            return {"interval_seconds": get_interval_seconds(config)}
        if method == "PUT":
            payload = self._read_json_body()
            seconds = int(payload.get("seconds") or 0)
            if seconds < 5:
                raise ApiError(HTTPStatus.BAD_REQUEST, "seconds must be >= 5")
            config.setdefault("poll", {})["interval_seconds"] = seconds
            save_config(self.server.config_path, config)
            result = {"action": "updated", "interval_seconds": seconds}
            auth_store.write_audit_log(
                actor=context,
                action="update",
                resource="poll",
                resource_id="interval_seconds",
                detail=result,
                ip=self._client_ip(),
            )
            return result
        raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Unsupported poll method")

    def _handle_proxy(
        self,
        method: str,
        config: Dict[str, Any],
        context: AuthContext,
        auth_store: AuthStore,
    ) -> Dict[str, Any]:
        self._require_permission(context, "proxy_manage")
        if method == "GET":
            return get_proxy_config_for_api(config)
        if method == "PUT":
            payload = self._read_json_body()
            result = update_proxy_config(config, payload)
            save_config(self.server.config_path, config)
            auth_store.write_audit_log(
                actor=context,
                action="update",
                resource="proxy",
                resource_id="config",
                detail={"payload": payload, "result": result},
                ip=self._client_ip(),
            )
            return result
        raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Unsupported proxy method")

    def _build_dashboard(self, config: Dict[str, Any], context: AuthContext) -> Dict[str, Any]:
        targets = self._build_target_views(config) if context.can("targets_read") else []
        summary = self._build_summary_from_targets(targets)
        return {
            "generated_at": self._now_iso(),
            "summary": summary,
            "targets": targets,
            "notify_groups": list_notify_groups(config) if context.can("webhook_manage") else [],
            "poll": {"interval_seconds": get_interval_seconds(config)}
            if context.can("poll_manage")
            else {"interval_seconds": 0},
            "proxy": get_proxy_config_for_api(config)
            if context.can("proxy_manage")
            else self._masked_proxy_view(),
            "admin_api": get_admin_api_config_for_api(config),
        }

    def _masked_proxy_view(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "provider": "",
            "request_method": "GET",
            "api_url": "",
            "api_key_header": "",
            "api_key_configured": False,
            "extra_headers": {},
            "query_params": {},
            "request_body": {},
            "response_data_path": "",
            "response_fields": {},
            "cache_seconds": 0,
            "timeout_seconds": 0,
            "sticky_mode": "shared",
            "verify_ssl": True,
        }

    def _build_summary(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return self._build_summary_from_targets(self._build_target_views(config))

    def _build_summary_from_targets(self, target_views: List[Dict[str, Any]]) -> Dict[str, Any]:
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
            group_keys = list(row.get("group_keys") or [])
            group_names = [group_lookup.get(key, key) for key in group_keys]
            state = states.get(str(row.get("activity_id") or ""), {})
            enriched.append(
                {
                    **row,
                    "group_names": group_names,
                    "group_name": group_names[0] if group_names else group_lookup.get(row.get("group_key"), row.get("group_key")),
                    "last_state": state.get("last_state") or "UNKNOWN",
                    "last_sold_out": state.get("last_sold_out"),
                    "last_title": state.get("last_title") or "",
                    "last_change_ts": state.get("last_change_ts") or "",
                    "last_error_text": state.get("last_error_text") or "",
                    "last_error_streak": int(state.get("last_error_streak") or 0),
                    "fail_count": int(state.get("fail_count") or 0),
                    "disabled_reason": state.get("disabled_reason") or "",
                    "consecutive_null_brief_count": int(state.get("consecutive_null_brief_count") or 0),
                }
            )
        # Keep the newest targets first in admin views.
        enriched.sort(key=lambda item: int(item.get("index") or 0), reverse=True)
        return enriched

    def _load_state_snapshot(self, db_path: str) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(db_path):
            return {}
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            try:
                rows = conn.execute(
                    """
                    SELECT activity_id, last_state, last_sold_out, last_title, last_change_ts,
                           last_error_text, last_error_streak, fail_count,
                           disabled_reason, consecutive_null_brief_count
                    FROM target_state
                    """
                ).fetchall()
            except sqlite3.OperationalError:
                rows = conn.execute(
                    """
                    SELECT activity_id, last_state, last_sold_out, last_title, last_change_ts,
                           last_error_text, last_error_streak, fail_count
                    FROM target_state
                    """
                ).fetchall()
            return {str(row["activity_id"]): dict(row) for row in rows}
        except sqlite3.OperationalError:
            return {}
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
        max_body_bytes = self._max_body_bytes()
        raw_length = str(self.headers.get("Content-Length", "") or "").strip()
        if not raw_length:
            return {}
        try:
            content_length = int(raw_length)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid Content-Length") from exc
        if content_length < 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
        if content_length == 0:
            return {}
        if content_length > max_body_bytes:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"请求体超过限制（最大 {max_body_bytes} 字节）")
        raw_bytes = self.rfile.read(content_length)
        if len(raw_bytes) != content_length:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Request body truncated")
        try:
            raw = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Request body must be UTF-8 JSON") from exc
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

    def _client_ip(self) -> str:
        forwarded = str(self.headers.get("X-Forwarded-For", "")).strip()
        if forwarded:
            return forwarded.split(",")[0].strip()
        return str(self.client_address[0] if self.client_address else "")

    def _now_iso(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description="dzdp monitor admin API")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--host", default=None, help="Override listen host")
    parser.add_argument("--port", default=None, type=int, help="Override listen port")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"配置文件不存在: {args.config}")
        return 1

    config = load_config(args.config)
    normalize_config_in_place(config)
    log_level = str(config.get("log_level", "INFO")).upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format="%(asctime)s | %(levelname)s | %(message)s")

    admin_api = config.get("admin_api", {}) or {}
    host = str(args.host if args.host is not None else (admin_api.get("listen_host", "127.0.0.1") or "127.0.0.1"))
    port = int(args.port if args.port is not None else (admin_api.get("listen_port", 8787) or 8787))
    if not 1 <= port <= 65535:
        print(f"端口非法: {port}（允许范围 1-65535）")
        return 1
    auth_store = AuthStore(
        db_path=str(config.get("sqlite_path") or "data/monitor_state.db"),
        session_ttl_hours=int(admin_api.get("session_ttl_hours", 1440) or 1440),
        default_admin_username=str(admin_api.get("default_admin_username", "admin")),
        default_admin_password=str(admin_api.get("default_admin_password", "")),
        legacy_auth_token=str(admin_api.get("auth_token", "")),
    )
    auth_store.ensure_schema_and_admin()

    httpd = DzdpAdminServer((host, port), AdminApiHandler, os.path.abspath(args.config))
    listen_host, listen_port = httpd.server_address[:2]
    logging.info(
        "Admin API listening on http://%s:%s (config=%s)",
        listen_host,
        listen_port,
        os.path.abspath(args.config),
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("Admin API stopped by user")
        return 0
    finally:
        httpd.server_close()


if __name__ == "__main__":
    sys.exit(main())
