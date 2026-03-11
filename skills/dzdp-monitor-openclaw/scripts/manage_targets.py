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
    add_target,
    list_targets,
    load_config,
    normalize_config_in_place,
    remove_target,
    resolve_target_index,
    save_config,
    update_target,
)


def print_payload(payload: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(payload)


def cmd_list(config: Dict[str, Any], as_json: bool) -> int:
    rows = list_targets(config)
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("No targets")
        return 0
    for row in rows:
        group_text = ",".join(row.get("group_keys") or []) or row["group_key"] or "-"
        print(
            f"{row['index']}. activity_id={row['activity_id'] or '-'}"
            f" | name={row['name'] or '-'} | groups={group_text} | url={row['url'] or '-'}"
        )
    return 0


def cmd_get(
    config: Dict[str, Any],
    *,
    activity_id: Optional[str],
    index: Optional[int],
    name: Optional[str],
    url: Optional[str],
    as_json: bool,
) -> int:
    rows = list_targets(config)
    idx, err = resolve_target_index(
        config.get("targets", []),
        activity_id=activity_id,
        index=index,
        name=name,
        url=url,
    )
    if idx < 0:
        print(err, file=sys.stderr)
        return 2
    target = rows[idx]
    if as_json:
        print(json.dumps(target, ensure_ascii=False, indent=2))
    else:
        group_text = ",".join(target.get("group_keys") or []) or target["group_key"] or "-"
        print(
            f"{target['index']}. activity_id={target['activity_id'] or '-'}"
            f" | name={target['name'] or '-'} | groups={group_text} | url={target['url'] or '-'}"
        )
    return 0


def cmd_add(
    config: Dict[str, Any],
    *,
    url: str,
    name: Optional[str],
    activity_id: Optional[str],
    group_key: Optional[str],
    upsert: bool,
    as_json: bool,
) -> int:
    payload = add_target(
        config,
        url=url,
        name=name,
        activity_id=activity_id,
        group_keys_values=None,
        group_key_value=group_key,
        upsert=upsert,
    )
    print_payload(payload, as_json)
    return 0


def cmd_update(
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
    as_json: bool,
) -> int:
    payload = update_target(
        config,
        activity_id=activity_id,
        index=index,
        selector_name=selector_name,
        selector_url=selector_url,
        set_name=set_name,
        set_url=set_url,
        new_activity_id=new_activity_id,
        set_group_keys=None,
        set_group_key=set_group_key,
    )
    print_payload(payload, as_json)
    return 0


def cmd_remove(
    config: Dict[str, Any],
    *,
    activity_id: Optional[str],
    index: Optional[int],
    name: Optional[str],
    url: Optional[str],
    as_json: bool,
) -> int:
    payload = remove_target(
        config,
        activity_id=activity_id,
        index=index,
        name=name,
        url=url,
    )
    print_payload(payload, as_json)
    return 0


def build_parser(default_config: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage dzdp monitor targets in config.json")
    parser.add_argument("--config", default=default_config, help="Path to config.json")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="List all targets")
    list_p.add_argument("--json", action="store_true", help="Output JSON")

    get_p = sub.add_parser("get", help="Get one target by selector")
    get_selector = get_p.add_mutually_exclusive_group(required=True)
    get_selector.add_argument("--activity-id")
    get_selector.add_argument("--index", type=int)
    get_selector.add_argument("--name")
    get_selector.add_argument("--url")
    get_p.add_argument("--json", action="store_true", help="Output JSON")

    add_p = sub.add_parser("add", help="Add a target")
    add_p.add_argument("--url", required=True)
    add_p.add_argument("--name")
    add_p.add_argument("--activity-id")
    add_p.add_argument("--group-key")
    add_p.add_argument("--upsert", action="store_true", help="Update if exists")
    add_p.add_argument("--json", action="store_true", help="Output JSON")

    upd_p = sub.add_parser("update", help="Update a target by selector")
    upd_selector = upd_p.add_mutually_exclusive_group(required=True)
    upd_selector.add_argument("--activity-id", help="Existing activity_id")
    upd_selector.add_argument("--index", type=int, help="Existing 1-based index")
    upd_selector.add_argument("--name", dest="selector_name", help="Existing name")
    upd_selector.add_argument("--url", dest="selector_url", help="Existing url")
    upd_p.add_argument("--set-name")
    upd_p.add_argument("--set-url")
    upd_p.add_argument("--new-activity-id")
    upd_p.add_argument("--set-group-key")
    upd_p.add_argument("--json", action="store_true", help="Output JSON")

    rm_p = sub.add_parser("remove", help="Remove a target by selector")
    rm_selector = rm_p.add_mutually_exclusive_group(required=True)
    rm_selector.add_argument("--activity-id")
    rm_selector.add_argument("--index", type=int)
    rm_selector.add_argument("--name")
    rm_selector.add_argument("--url")
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

        if args.command == "get":
            rc = cmd_get(
                config,
                activity_id=getattr(args, "activity_id", None),
                index=getattr(args, "index", None),
                name=getattr(args, "name", None),
                url=getattr(args, "url", None),
                as_json=as_json,
            )
            if normalized_changed:
                save_config(args.config, config)
            return rc

        if args.command == "add":
            rc = cmd_add(
                config,
                url=args.url,
                name=args.name,
                activity_id=args.activity_id,
                group_key=args.group_key,
                upsert=args.upsert,
                as_json=as_json,
            )
            save_config(args.config, config)
            return rc

        if args.command == "update":
            rc = cmd_update(
                config,
                activity_id=getattr(args, "activity_id", None),
                index=getattr(args, "index", None),
                selector_name=getattr(args, "selector_name", None),
                selector_url=getattr(args, "selector_url", None),
                set_name=args.set_name,
                set_url=args.set_url,
                new_activity_id=args.new_activity_id,
                set_group_key=args.set_group_key,
                as_json=as_json,
            )
            save_config(args.config, config)
            return rc

        if args.command == "remove":
            rc = cmd_remove(
                config,
                activity_id=getattr(args, "activity_id", None),
                index=getattr(args, "index", None),
                name=getattr(args, "name", None),
                url=getattr(args, "url", None),
                as_json=as_json,
            )
            save_config(args.config, config)
            return rc

        print(f"Unsupported command: {args.command}", file=sys.stderr)
        return 2
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
