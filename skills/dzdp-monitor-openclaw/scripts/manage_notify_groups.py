#!/usr/bin/env python3
import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app_config import (  # noqa: E402
    ConfigError,
    add_notify_group,
    list_notify_groups,
    load_config,
    normalize_config_in_place,
    remove_notify_group,
    save_config,
    update_notify_group,
)


def print_payload(payload: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(payload)


def cmd_list(config: Dict[str, Any], as_json: bool) -> int:
    rows = list_notify_groups(config)
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for row in rows:
        default_flag = " default" if row.get("is_default") else ""
        print(
            f"{row['key']} | name={row['name']} | webhook={row['webhook_masked'] or '-'} | configured={row['webhook_configured']}{default_flag}"
        )
    return 0


def cmd_add(config: Dict[str, Any], *, key: Optional[str], name: str, webhook: str, as_json: bool) -> int:
    payload = add_notify_group(config, key_value=key, name=name, webhook=webhook)
    print_payload(payload, as_json)
    return 0


def cmd_update(
    config: Dict[str, Any],
    *,
    key: str,
    set_name: Optional[str],
    set_webhook: Optional[str],
    make_default: bool,
    as_json: bool,
) -> int:
    payload = update_notify_group(
        config,
        key_value=key,
        set_name=set_name,
        set_webhook=set_webhook,
        make_default=True if make_default else None,
    )
    print_payload(payload, as_json)
    return 0


def cmd_remove(config: Dict[str, Any], *, key: str, as_json: bool) -> int:
    payload = remove_notify_group(config, key_value=key)
    print_payload(payload, as_json)
    return 0


def build_parser(default_config: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage dzdp monitor notify groups in config.json")
    parser.add_argument("--config", default=default_config, help="Path to config.json")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="List notify groups")
    list_p.add_argument("--json", action="store_true", help="Output JSON")

    add_p = sub.add_parser("add", help="Add a notify group")
    add_p.add_argument("--key")
    add_p.add_argument("--name", required=True)
    add_p.add_argument("--webhook", default="")
    add_p.add_argument("--json", action="store_true", help="Output JSON")

    upd_p = sub.add_parser("update", help="Update a notify group")
    upd_p.add_argument("--key", required=True)
    upd_p.add_argument("--set-name")
    upd_p.add_argument("--set-webhook")
    upd_p.add_argument("--make-default", action="store_true")
    upd_p.add_argument("--json", action="store_true", help="Output JSON")

    rm_p = sub.add_parser("remove", help="Remove a notify group")
    rm_p.add_argument("--key", required=True)
    rm_p.add_argument("--json", action="store_true", help="Output JSON")

    return parser


def main() -> int:
    default_config = os.path.abspath(os.path.join(SCRIPT_DIR, "../../../config.json"))
    parser = build_parser(default_config)
    args = parser.parse_args()
    as_json = bool(getattr(args, "json", False))

    try:
        config = load_config(args.config)
        normalized_changed = normalize_config_in_place(config)

        if args.command == "list":
            rc = cmd_list(config, as_json)
            if normalized_changed:
                save_config(args.config, config)
            return rc

        if args.command == "add":
            rc = cmd_add(config, key=args.key, name=args.name, webhook=args.webhook, as_json=as_json)
            save_config(args.config, config)
            return rc

        if args.command == "update":
            rc = cmd_update(
                config,
                key=args.key,
                set_name=args.set_name,
                set_webhook=args.set_webhook,
                make_default=args.make_default,
                as_json=as_json,
            )
            save_config(args.config, config)
            return rc

        if args.command == "remove":
            rc = cmd_remove(config, key=args.key, as_json=as_json)
            save_config(args.config, config)
            return rc

        print(f"Unsupported command: {args.command}", file=sys.stderr)
        return 2
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
