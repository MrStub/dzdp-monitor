#!/usr/bin/env python3
import argparse
import hashlib
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
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

import requests

API_ENDPOINT = "https://m.dianping.com/bwc/customer/loadVipLaunchProductBriefInfo"
EPHEMERAL_QUERY_KEYS = {"shareid", "shareId"}
DEFAULT_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1"
)


def now_local() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def today_local() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def parse_activity_id(url: str, explicit_activity_id: Optional[str] = None) -> Optional[str]:
    if explicit_activity_id:
        return str(explicit_activity_id).strip()
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    for key in ("activityid", "activityId"):
        if key in q and q[key]:
            return q[key][0].strip()
    return None


def normalize_target_url(url: str) -> str:
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
        existing_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(target_state)")
        }
        required_columns = {
            "last_error_text": "TEXT",
            "last_error_date": "TEXT",
            "last_error_streak": "INTEGER NOT NULL DEFAULT 0",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                self.conn.execute(
                    f"ALTER TABLE target_state ADD COLUMN {column_name} {column_type}"
                )

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
        error_streak = (
            previous_error_streak + 1
            if previous_error_text == error_text and previous_error_date == alert_date
            else 1
        )

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
            already_alerted_today=self.has_error_alerted_today(
                target.activity_id,
                error_text,
                alert_date,
            ),
            alert_date=alert_date,
        )

    def has_error_alerted_today(
        self,
        activity_id: str,
        error_text: str,
        alert_date: Optional[str] = None,
    ) -> bool:
        cur = self.conn.execute(
            """
            SELECT 1
            FROM failure_alert_history
            WHERE activity_id = ? AND error_signature = ? AND alert_date = ?
            LIMIT 1
            """,
            (
                activity_id,
                error_signature(error_text),
                alert_date or today_local(),
            ),
        )
        return cur.fetchone() is not None

    def mark_error_alerted(
        self,
        target: Target,
        error_text: str,
        alert_date: Optional[str] = None,
    ) -> None:
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


def notify_all(
    config: Dict[str, Any],
    subject: str,
    body: str,
    feishu_text: Optional[str] = None,
) -> bool:
    notify_cfg = config.get("notify", {})
    any_sent = False

    feishu_webhook = notify_cfg.get("feishu_webhook", "")
    if feishu_webhook:
        text = feishu_text if feishu_text is not None else f"{subject}\n{body}"
        ok, detail = send_feishu(feishu_webhook, text)
        if ok:
            logging.info("Feishu notification sent")
            any_sent = True
        else:
            logging.error("Feishu notification failed: %s", detail)

    email_cfg = notify_cfg.get("email", {})
    if email_cfg.get("enabled", False):
        ok, detail = send_email(email_cfg, subject, body)
        if ok:
            logging.info("Email notification sent")
            any_sent = True
        else:
            logging.error("Email notification failed: %s", detail)
    return any_sent


def fetch_product_brief(
    session: requests.Session,
    activity_id: str,
    timeout_seconds: int,
) -> Tuple[bool, Dict[str, Any], str]:
    params = {"activityId": activity_id, "source": "share"}
    try:
        resp = session.get(API_ENDPOINT, params=params, timeout=timeout_seconds)
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


def render_product_summary(target: Target, product: Dict[str, Any], state: str) -> str:
    sold_info = product.get("soldInfo") or {}
    price = product.get("priceInfo") or {}
    shops = ((product.get("activityShopModule") or {}).get("activityShopInfoList") or [])
    shop = shops[0] if shops else {}

    lines = [
        f"监控项: {target.name}",
        f"活动ID: {target.activity_id}",
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
        lines.insert(4, f"半年售: {sold_info.get('halfYearSoldNum')}")
    return "\n".join(lines)


def render_in_stock_alert(target: Target, product: Dict[str, Any]) -> str:
    configured_name = str(target.name or "").strip() or "(未命名监控项)"
    api_title = str(product.get("title") or "").strip()

    lines = [
        "检测到套餐有货",
        f"套餐名: {configured_name}",
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
        f"链接: {target.url}",
        f"相同报错当日连续次数: {error_streak}",
        f"错误: {error_text}",
        f"时间: {now_local()}",
    ]
    return "\n".join(lines)


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_targets(config: Dict[str, Any]) -> List[Target]:
    targets_cfg = config.get("targets", [])
    if not targets_cfg:
        raise ValueError("config.targets 不能为空")

    targets: List[Target] = []
    for i, item in enumerate(targets_cfg, start=1):
        url = normalize_target_url(str(item.get("url", "")).strip())
        if not url:
            raise ValueError(f"targets[{i}] 缺少 url")
        activity_id = parse_activity_id(url, item.get("activity_id"))
        if not activity_id:
            raise ValueError(
                f"targets[{i}] 无法解析 activityid，请在配置中显式提供 activity_id"
            )
        name = str(item.get("name", f"target-{activity_id}")).strip()
        targets.append(Target(name=name, url=url, activity_id=activity_id))
    return targets


def run_cycle(
    config: Dict[str, Any],
    targets: List[Target],
    store: StateStore,
    session: requests.Session,
) -> None:
    poll_cfg = config.get("poll", {})
    timeout_seconds = int(poll_cfg.get("timeout_seconds", 10))
    jitter_seconds = float(poll_cfg.get("request_jitter_seconds", 0))

    alerts_cfg = config.get("alerts", {})
    notify_on_states = set(alerts_cfg.get("notify_on_states", ["IN_STOCK"]))
    notify_on_first_seen = bool(alerts_cfg.get("notify_on_first_seen", True))
    failure_threshold = max(1, int(alerts_cfg.get("failure_threshold", 5)))
    notify_failures = bool(alerts_cfg.get("notify_failures", False))

    for idx, target in enumerate(targets):
        ok, data, err = fetch_product_brief(session, target.activity_id, timeout_seconds)
        if not ok:
            failure = store.record_failure(target, err)
            logging.warning(
                "[%s] check failed (fail_count=%s same_error_streak=%s): %s",
                target.name,
                failure.fail_count,
                failure.error_streak,
                err,
            )
            should_alert = (
                notify_failures
                and failure.error_streak >= failure_threshold
                and not failure.already_alerted_today
            )
            if should_alert:
                subject = f"[点评库存监控异常] {target.name}"
                body = render_failure_alert(target, err, failure.error_streak)
                sent = notify_all(config, subject, body, feishu_text=body)
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

        logging.info("[%s] state=%s soldOut=%s title=%s", target.name, state, sold_out, title)

        if changed:
            if old is None and not notify_on_first_seen:
                pass
            elif state in notify_on_states:
                subject = f"[点评库存] {state_to_cn(state)} - {target.name}"
                body = render_in_stock_alert(target, product)
                notify_all(config, subject, body, feishu_text=body)

        if idx < len(targets) - 1 and jitter_seconds > 0:
            time.sleep(random.uniform(0, jitter_seconds))


def build_requests_session(config: Dict[str, Any]) -> requests.Session:
    sess = requests.Session()
    headers = config.get("request_headers", {})
    ua = headers.get("User-Agent", DEFAULT_UA)
    default_headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
    }
    default_headers.update(headers)
    sess.headers.update(default_headers)
    return sess


def target_signature(targets: List[Target]) -> Tuple[Tuple[str, str, str], ...]:
    return tuple((target.activity_id, target.name, target.url) for target in targets)


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
    last_signature: Optional[Tuple[Tuple[str, str, str], ...]] = None

    try:
        if args.once:
            targets = build_targets(config)
            logging.info("Loaded %s targets", len(targets))
            for target in targets:
                logging.info("Target: %s | activity_id=%s", target.name, target.activity_id)
            session = build_requests_session(config)
            run_cycle(config, targets, store, session)
            session.close()
            return 0

        while True:
            config = load_config(args.config)
            targets = build_targets(config)
            signature = target_signature(targets)
            if signature != last_signature:
                logging.info("Reloaded %s targets from config", len(targets))
                for target in targets:
                    logging.info("Target: %s | activity_id=%s", target.name, target.activity_id)
                last_signature = signature

            interval_seconds = int((config.get("poll", {}) or {}).get("interval_seconds", 60))
            interval_seconds = max(5, interval_seconds)
            session = build_requests_session(config)
            start = time.time()
            run_cycle(config, targets, store, session)
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
