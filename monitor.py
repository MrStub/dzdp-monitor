#!/usr/bin/env python3
import argparse
import hashlib
import itertools
import json
import logging
import os
import random
import smtplib
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple

import requests

from app_config import (
    get_interval_seconds,
    list_targets,
    load_config,
    normalize_config_in_place,
    resolve_target_feishu_webhooks,
)
from proxy_provider import ProxyResolutionError, ProxyResolver

API_ENDPOINT = "https://m.dianping.com/bwc/customer/loadVipLaunchProductBriefInfo"
DEFAULT_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1"
)
DEFAULT_UA_POOL = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; M2012K11AC) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
]
UA_STICKY_MAP: Dict[str, str] = {}


def build_generated_ua_pool(max_size: int = 400) -> List[str]:
    ios_versions = ["16_7", "17_0", "17_3", "17_6", "18_0", "18_1", "18_2"]
    ios_safari = ["16.6", "17.0", "17.3", "17.6", "18.0", "18.1", "18.2"]
    ios_devices = [
        "iPhone",
        "iPhone14,2",
        "iPhone15,2",
        "iPhone16,1",
        "iPhone16,2",
    ]

    android_versions = ["11", "12", "13", "14", "15"]
    android_models = [
        "Pixel 6",
        "Pixel 7",
        "Pixel 8",
        "SM-S9180",
        "SM-S9280",
        "M2012K11AC",
        "V2307A",
        "PJD110",
    ]
    chrome_majors = ["124", "125", "126", "127", "128", "129", "130", "131", "132", "133"]

    uas: List[str] = []

    for ios_ver, safari_ver, dev in itertools.product(ios_versions, ios_safari, ios_devices):
        uas.append(
            "Mozilla/5.0 "
            f"({dev}; CPU iPhone OS {ios_ver} like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            f"Version/{safari_ver} Mobile/15E148 Safari/604.1"
        )

    for and_ver, model, chrome_major in itertools.product(android_versions, android_models, chrome_majors):
        uas.append(
            "Mozilla/5.0 "
            f"(Linux; Android {and_ver}; {model}) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_major}.0.0.0 Mobile Safari/537.36"
        )

    deduped = list(dict.fromkeys(uas))
    random.shuffle(deduped)
    return deduped[: max(50, int(max_size))]


def now_local() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def today_local() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def error_signature(error_text: str) -> str:
    return hashlib.sha1(str(error_text).strip().encode("utf-8")).hexdigest()


def stock_state_from_sold_out(sold_out: Any) -> str:
    if sold_out == 0:
        return "IN_STOCK"
    if sold_out == 1:
        return "SOLD_OUT"
    return "UNKNOWN"


def state_to_cn(state: str) -> str:
    if state == "IN_STOCK":
        return "有货"
    if state == "SOLD_OUT":
        return "售罄"
    return "未知"


@dataclass
class Target:
    name: str
    url: str
    activity_id: str
    group_keys: List[str]

    def to_config_target(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "activity_id": self.activity_id,
            "group_keys": self.group_keys,
        }


@dataclass
class FailureRecord:
    fail_count: int
    error_streak: int
    already_alerted_today: bool
    alert_date: str


class StateStore:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS target_state (
                activity_id TEXT PRIMARY KEY,
                target_name TEXT NOT NULL,
                target_url TEXT NOT NULL,
                last_state TEXT,
                last_sold_out INTEGER,
                last_title TEXT,
                last_payload_json TEXT,
                last_change_ts TEXT,
                last_error_text TEXT,
                last_error_date TEXT,
                last_error_streak INTEGER NOT NULL DEFAULT 0,
                fail_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        existing_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(target_state)")}
        required_columns = {
            "last_error_text": "TEXT",
            "last_error_date": "TEXT",
            "last_error_streak": "INTEGER NOT NULL DEFAULT 0",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                self.conn.execute(f"ALTER TABLE target_state ADD COLUMN {column_name} {column_type}")

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS failure_alert_history (
                activity_id TEXT NOT NULL,
                error_signature TEXT NOT NULL,
                error_text TEXT NOT NULL,
                alert_date TEXT NOT NULL,
                alert_ts TEXT NOT NULL,
                PRIMARY KEY (activity_id, error_signature, alert_date)
            )
            """
        )
        self.conn.commit()

    def get(self, activity_id: str) -> Optional[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM target_state WHERE activity_id = ?",
            (activity_id,),
        )
        return cur.fetchone()

    def upsert_success(
        self,
        target: Target,
        state: str,
        sold_out: Optional[int],
        title: str,
        payload: Dict[str, Any],
        changed: bool,
    ) -> None:
        old = self.get(target.activity_id)
        last_change_ts = now_local() if changed or old is None else old["last_change_ts"]
        self.conn.execute(
            """
            INSERT INTO target_state (
                activity_id, target_name, target_url, last_state, last_sold_out,
                last_title, last_payload_json, last_change_ts,
                last_error_text, last_error_date, last_error_streak, fail_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, 0)
            ON CONFLICT(activity_id) DO UPDATE SET
                target_name=excluded.target_name,
                target_url=excluded.target_url,
                last_state=excluded.last_state,
                last_sold_out=excluded.last_sold_out,
                last_title=excluded.last_title,
                last_payload_json=excluded.last_payload_json,
                last_change_ts=excluded.last_change_ts,
                last_error_text=NULL,
                last_error_date=NULL,
                last_error_streak=0,
                fail_count=0
            """,
            (
                target.activity_id,
                target.name,
                target.url,
                state,
                sold_out,
                title,
                json.dumps(payload, ensure_ascii=False),
                last_change_ts,
            ),
        )
        self.conn.commit()

    def record_failure(self, target: Target, error_text: str) -> FailureRecord:
        row = self.get(target.activity_id)
        fail_count = 1 if row is None else int(row["fail_count"] or 0) + 1
        alert_date = today_local()
        previous_error_text = "" if row is None else str(row["last_error_text"] or "")
        previous_error_date = "" if row is None else str(row["last_error_date"] or "")
        previous_error_streak = 0 if row is None else int(row["last_error_streak"] or 0)
        error_streak = previous_error_streak + 1 if previous_error_text == error_text and previous_error_date == alert_date else 1

        if row is None:
            self.conn.execute(
                """
                INSERT INTO target_state (
                    activity_id, target_name, target_url,
                    last_error_text, last_error_date, last_error_streak, fail_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target.activity_id,
                    target.name,
                    target.url,
                    error_text,
                    alert_date,
                    error_streak,
                    fail_count,
                ),
            )
        else:
            self.conn.execute(
                """
                UPDATE target_state
                SET target_name=?, target_url=?, last_error_text=?, last_error_date=?,
                    last_error_streak=?, fail_count=?
                WHERE activity_id=?
                """,
                (
                    target.name,
                    target.url,
                    error_text,
                    alert_date,
                    error_streak,
                    fail_count,
                    target.activity_id,
                ),
            )
        self.conn.commit()
        return FailureRecord(
            fail_count=fail_count,
            error_streak=error_streak,
            already_alerted_today=self.has_error_alerted_today(target.activity_id, error_text, alert_date),
            alert_date=alert_date,
        )

    def has_error_alerted_today(self, activity_id: str, error_text: str, alert_date: Optional[str] = None) -> bool:
        cur = self.conn.execute(
            """
            SELECT 1
            FROM failure_alert_history
            WHERE activity_id = ? AND error_signature = ? AND alert_date = ?
            LIMIT 1
            """,
            (activity_id, error_signature(error_text), alert_date or today_local()),
        )
        return cur.fetchone() is not None

    def mark_error_alerted(self, target: Target, error_text: str, alert_date: Optional[str] = None) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO failure_alert_history (
                activity_id, error_signature, error_text, alert_date, alert_ts
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                target.activity_id,
                error_signature(error_text),
                error_text,
                alert_date or today_local(),
                now_local(),
            ),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def send_feishu(webhook: str, text: str, timeout: int = 8) -> Tuple[bool, str]:
    if not webhook:
        return False, "feishu webhook empty"
    try:
        resp = requests.post(
            webhook,
            json={"msg_type": "text", "content": {"text": text}},
            timeout=timeout,
        )
        ok = resp.status_code == 200
        return ok, f"status={resp.status_code} body={resp.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def send_email(email_cfg: Dict[str, Any], subject: str, body: str) -> Tuple[bool, str]:
    if not email_cfg.get("enabled", False):
        return False, "email disabled"

    host = email_cfg.get("smtp_host", "")
    port = int(email_cfg.get("smtp_port", 587))
    username = email_cfg.get("username", "")
    password = email_cfg.get("password", "")
    from_addr = email_cfg.get("from_addr", username)
    to_addrs = email_cfg.get("to_addrs", [])
    use_ssl = bool(email_cfg.get("use_ssl", False))
    use_tls = bool(email_cfg.get("use_tls", True))

    if not host or not from_addr or not to_addrs:
        return False, "email config incomplete"

    msg = MIMEText(body, _subtype="plain", _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            if use_tls:
                server.starttls()
        if username and password:
            server.login(username, password)
        server.sendmail(from_addr, to_addrs, msg.as_string())
        server.quit()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def notify_channels(
    config: Dict[str, Any],
    subject: str,
    body: str,
    *,
    feishu_text: Optional[str] = None,
    feishu_webhooks: Optional[List[str]] = None,
) -> bool:
    notify_cfg = config.get("notify", {}) or {}
    any_sent = False

    text = feishu_text if feishu_text is not None else f"{subject}\n{body}"
    seen_webhooks = set()
    for raw_webhook in feishu_webhooks or []:
        effective_webhook = str(raw_webhook or "").strip()
        if not effective_webhook or effective_webhook in seen_webhooks:
            continue
        seen_webhooks.add(effective_webhook)
        ok, detail = send_feishu(effective_webhook, text)
        if ok:
            logging.info("Feishu notification sent")
            any_sent = True
        else:
            logging.error("Feishu notification failed: %s", detail)

    email_cfg = notify_cfg.get("email", {}) or {}
    if email_cfg.get("enabled", False):
        ok, detail = send_email(email_cfg, subject, body)
        if ok:
            logging.info("Email notification sent")
            any_sent = True
        else:
            logging.error("Email notification failed: %s", detail)
    return any_sent


def notify_target(config: Dict[str, Any], target: Target, subject: str, body: str) -> bool:
    target_webhooks = resolve_target_feishu_webhooks(config, target.to_config_target())
    return notify_channels(
        config,
        subject,
        body,
        feishu_text=body,
        feishu_webhooks=target_webhooks,
    )


def fetch_product_brief(
    session: requests.Session,
    activity_id: str,
    timeout_seconds: int,
    *,
    proxies: Optional[Dict[str, str]] = None,
) -> Tuple[bool, Dict[str, Any], str]:
    params = {"activityId": activity_id, "source": "share"}
    try:
        resp = session.get(API_ENDPOINT, params=params, timeout=timeout_seconds, proxies=proxies)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return False, {}, f"request error: {exc}"

    if data.get("code") != 200:
        return False, data, f"api code != 200, code={data.get('code')} msg={data.get('msg')}"

    product = ((data.get("data") or {}).get("productBriefInfo")) or None
    if not product:
        return False, data, "productBriefInfo is null (可能是链接类型不匹配或需要登录态)"

    return True, product, ""


def format_target_groups(target: Target) -> str:
    return ", ".join(target.group_keys) if target.group_keys else "default"


def render_product_summary(target: Target, product: Dict[str, Any], state: str) -> str:
    sold_info = product.get("soldInfo") or {}
    price = product.get("priceInfo") or {}
    shops = ((product.get("activityShopModule") or {}).get("activityShopInfoList") or [])
    shop = shops[0] if shops else {}

    lines = [
        f"监控项: {target.name}",
        f"活动ID: {target.activity_id}",
        f"通知分组: {format_target_groups(target)}",
        f"库存状态: {state_to_cn(state)}",
        f"套餐名称: {product.get('title') or '-'}",
        (
            "价格: 原价 {retail} | 美团价 {mt} | 优惠 {minus} | 到手 {final}"
        ).format(
            retail=price.get("retailPrice", "-"),
            mt=price.get("mtPrice", "-"),
            minus=price.get("minusPrice", "-"),
            final=price.get("finalPrice", "-"),
        ),
        (
            "门店: {shop_name} | 区域: {region} | 地址: {addr}"
        ).format(
            shop_name=shop.get("shopName", "-"),
            region=shop.get("mainRegionName", "-"),
            addr=shop.get("address", "-"),
        ),
        f"城市ID: {shop.get('cityId', '-')}",
        f"链接: {target.url}",
        f"时间: {now_local()}",
    ]
    if sold_info.get("halfYearSoldNum") is not None:
        lines.insert(5, f"半年售: {sold_info.get('halfYearSoldNum')}")
    return "\n".join(lines)


def render_in_stock_alert(target: Target, product: Dict[str, Any]) -> str:
    configured_name = str(target.name or "").strip() or "(未命名监控项)"
    api_title = str(product.get("title") or "").strip()

    lines = [
        "检测到套餐有货",
        f"套餐名: {configured_name}",
        f"通知分组: {format_target_groups(target)}",
    ]
    if api_title and api_title != configured_name:
        lines.append(f"接口名称: {api_title}")

    lines.extend([
        f"链接: {target.url}",
        f"时间: {now_local()}",
    ])
    return "\n".join(lines)


def render_failure_alert(target: Target, error_text: str, error_streak: int) -> str:
    lines = [
        "监控异常",
        f"监控项: {target.name}",
        f"通知分组: {format_target_groups(target)}",
        f"链接: {target.url}",
        f"相同报错当日连续次数: {error_streak}",
        f"错误: {error_text}",
        f"时间: {now_local()}",
    ]
    return "\n".join(lines)


def build_targets(config: Dict[str, Any]) -> List[Target]:
    normalize_config_in_place(config)
    rows = list_targets(config)
    if not rows:
        raise ValueError("config.targets 不能为空")

    targets: List[Target] = []
    for row in rows:
        activity_id = str(row.get("activity_id") or "").strip()
        if not activity_id:
            raise ValueError("存在监控项缺少 activity_id")
        targets.append(
            Target(
                name=str(row.get("name") or f"target-{activity_id}").strip(),
                url=str(row.get("url") or "").strip(),
                activity_id=activity_id,
                group_keys=[str(value).strip() for value in (row.get("group_keys") or []) if str(value).strip()],
            )
        )
    return targets


def run_cycle(
    config: Dict[str, Any],
    targets: List[Target],
    store: StateStore,
    session: requests.Session,
    proxy_resolver: ProxyResolver,
) -> None:
    poll_cfg = config.get("poll", {}) or {}
    timeout_seconds = int(poll_cfg.get("timeout_seconds", 10))
    jitter_seconds = float(poll_cfg.get("request_jitter_seconds", 0))

    alerts_cfg = config.get("alerts", {}) or {}
    notify_on_states = set(alerts_cfg.get("notify_on_states", ["IN_STOCK"]))
    notify_on_first_seen = bool(alerts_cfg.get("notify_on_first_seen", True))
    failure_threshold = max(1, int(alerts_cfg.get("failure_threshold", 5)))
    notify_failures = bool(alerts_cfg.get("notify_failures", False))

    for idx, target in enumerate(targets):
        session.headers["User-Agent"] = resolve_user_agent(config, target.activity_id)

        try:
            proxies = proxy_resolver.get_requests_proxies(config, target_key=target.activity_id)
        except ProxyResolutionError as exc:
            err = f"proxy resolve error: {exc}"
            failure = store.record_failure(target, err)
            logging.warning(
                "[%s] proxy resolution failed (fail_count=%s same_error_streak=%s): %s",
                target.name,
                failure.fail_count,
                failure.error_streak,
                err,
            )
            if notify_failures and failure.error_streak >= failure_threshold and not failure.already_alerted_today:
                subject = f"[点评库存监控异常] {target.name}"
                body = render_failure_alert(target, err, failure.error_streak)
                sent = notify_target(config, target, subject, body)
                if sent:
                    store.mark_error_alerted(target, err, failure.alert_date)
            if idx < len(targets) - 1 and jitter_seconds > 0:
                time.sleep(random.uniform(0, jitter_seconds))
            continue

        ok, data, err = fetch_product_brief(session, target.activity_id, timeout_seconds, proxies=proxies)
        if not ok:
            failure = store.record_failure(target, err)
            logging.warning(
                "[%s] check failed (fail_count=%s same_error_streak=%s): %s",
                target.name,
                failure.fail_count,
                failure.error_streak,
                err,
            )
            should_alert = notify_failures and failure.error_streak >= failure_threshold and not failure.already_alerted_today
            if should_alert:
                subject = f"[点评库存监控异常] {target.name}"
                body = render_failure_alert(target, err, failure.error_streak)
                sent = notify_target(config, target, subject, body)
                if sent:
                    store.mark_error_alerted(target, err, failure.alert_date)
            if idx < len(targets) - 1 and jitter_seconds > 0:
                time.sleep(random.uniform(0, jitter_seconds))
            continue

        product = data
        sold_out = (product.get("soldInfo") or {}).get("soldOut")
        state = stock_state_from_sold_out(sold_out)
        title = str(product.get("title") or "")

        old = store.get(target.activity_id)
        old_state = old["last_state"] if old else None
        changed = old_state != state

        store.upsert_success(
            target=target,
            state=state,
            sold_out=sold_out if isinstance(sold_out, int) else None,
            title=title,
            payload=product,
            changed=changed,
        )

        logging.info("[%s] state=%s soldOut=%s title=%s groups=%s", target.name, state, sold_out, title, format_target_groups(target))

        if changed:
            if old is None and not notify_on_first_seen:
                pass
            elif state in notify_on_states:
                subject = f"[点评库存] {state_to_cn(state)} - {target.name}"
                body = render_in_stock_alert(target, product)
                notify_target(config, target, subject, body)

        if idx < len(targets) - 1 and jitter_seconds > 0:
            time.sleep(random.uniform(0, jitter_seconds))


def resolve_user_agent(config: Dict[str, Any], target_key: Optional[str] = None) -> str:
    headers = config.get("request_headers", {}) or {}
    fixed_ua = str(headers.get("User-Agent") or DEFAULT_UA)

    ua_cfg = config.get("user_agent", {}) or {}
    mode = str(ua_cfg.get("mode", "fixed")).strip().lower()
    pool = [str(x).strip() for x in (ua_cfg.get("pool") or []) if str(x).strip()]
    generated_pool_size = int(ua_cfg.get("generated_pool_size", 400))
    generated_pool = build_generated_ua_pool(generated_pool_size)
    candidates = list(dict.fromkeys((pool or DEFAULT_UA_POOL) + generated_pool))

    if mode == "fixed":
        return fixed_ua

    if mode == "random_pool":
        return random.choice(candidates)

    if mode == "per_target_sticky":
        key = target_key or "__default__"
        if key not in UA_STICKY_MAP:
            UA_STICKY_MAP[key] = random.choice(candidates)
        return UA_STICKY_MAP[key]

    return fixed_ua


def build_requests_session(config: Dict[str, Any]) -> requests.Session:
    sess = requests.Session()
    headers = config.get("request_headers", {}) or {}
    ua = resolve_user_agent(config)
    default_headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
    }
    default_headers.update(headers)
    sess.headers.update(default_headers)
    return sess


def target_signature(targets: List[Target]) -> Tuple[Tuple[str, str, str, str], ...]:
    return tuple((target.activity_id, target.name, target.url, ",".join(target.group_keys)) for target in targets)


def main() -> int:
    parser = argparse.ArgumentParser(description="大众点评优惠套餐库存多目标监控")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--once", action="store_true", help="仅执行一次检测后退出")
    parser.add_argument("--test-email", action="store_true", help="仅测试邮件发送后退出")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"配置文件不存在: {args.config}")
        print("请先复制 config.example.json 为 config.json 并填写参数。")
        return 1

    config = load_config(args.config)
    log_level = str(config.get("log_level", "INFO")).upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    ua_cfg = config.get("user_agent", {}) or {}
    ua_mode = str(ua_cfg.get("mode", "fixed")).strip().lower()
    ua_pool_size = len(ua_cfg.get("pool") or [])
    generated_pool_size = int(ua_cfg.get("generated_pool_size", 400))
    effective_pool_size = len(list(dict.fromkeys((ua_cfg.get("pool") or []) + build_generated_ua_pool(generated_pool_size))))
    logging.info(
        "UA mode=%s custom_pool=%s generated_pool=%s effective_pool=%s",
        ua_mode,
        ua_pool_size,
        generated_pool_size,
        effective_pool_size,
    )

    db_path = config.get("sqlite_path", "data/monitor_state.db")

    if args.test_email:
        email_cfg = (config.get("notify", {}) or {}).get("email", {}) or {}
        subject = "[点评库存监控] 邮件通道测试"
        body = (
            "这是一封测试邮件。\n"
            f"时间: {now_local()}\n"
            "来源: dzdp-monitor monitor.py --test-email"
        )
        ok, detail = send_email(email_cfg, subject, body)
        if ok:
            print("EMAIL_TEST_OK")
            return 0
        print(f"EMAIL_TEST_FAIL: {detail}")
        return 2

    store = StateStore(db_path)
    proxy_resolver = ProxyResolver()
    last_signature: Optional[Tuple[Tuple[str, str, str, str], ...]] = None

    try:
        if args.once:
            targets = build_targets(config)
            logging.info("Loaded %s targets", len(targets))
            for target in targets:
                logging.info("Target: %s | activity_id=%s | groups=%s", target.name, target.activity_id, format_target_groups(target))
            session = build_requests_session(config)
            run_cycle(config, targets, store, session, proxy_resolver)
            session.close()
            return 0

        while True:
            config = load_config(args.config)
            targets = build_targets(config)
            signature = target_signature(targets)
            if signature != last_signature:
                logging.info("Reloaded %s targets from config", len(targets))
                for target in targets:
                    logging.info("Target: %s | activity_id=%s | groups=%s", target.name, target.activity_id, format_target_groups(target))
                last_signature = signature

            interval_seconds = get_interval_seconds(config)
            session = build_requests_session(config)
            start = time.time()
            run_cycle(config, targets, store, session, proxy_resolver)
            session.close()
            elapsed = time.time() - start
            sleep_for = max(0, interval_seconds - elapsed)
            logging.info("Cycle finished, sleep %.1fs", sleep_for)
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        logging.info("Stopped by user")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
