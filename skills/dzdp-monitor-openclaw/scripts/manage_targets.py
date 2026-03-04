#!/usr/bin/env python3
import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse


def parse_activity_id(url: str, explicit_activity_id: Optional[str] = None) -> Optional[str]:
    if explicit_activity_id:
        return str(explicit_activity_id).strip()
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    for key in ("activityid", "activityId"):
        if key in q and q[key]:
            return q[key][0].strip()
    return None


def load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def target_activity_id(target: Dict[str, Any]) -> Optional[str]:
    return parse_activity_id(str(target.get("url", "")), target.get("activity_id"))


def ensure_targets(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    targets = config.get("targets")
    if not isinstance(targets, list):
        config["targets"] = []
        targets = config["targets"]
    return targets


def find_target_index(targets: List[Dict[str, Any]], activity_id: str) -> int:
    for idx, t in enumerate(targets):
        if target_activity_id(t) == activity_id:
            return idx
    return -1


def format_target(idx: int, t: Dict[str, Any]) -> str:
    aid = target_activity_id(t) or "-"
    name = t.get("name", "-")
    url = t.get("url", "-")
    return f"{idx}. activity_id={aid} | name={name} | url={url}"


def cmd_list(targets: List[Dict[str, Any]], as_json: bool) -> int:
    rows = []
    for idx, t in enumerate(targets, start=1):
        rows.append(
            {
                "index": idx,
                "activity_id": target_activity_id(t),
                "name": t.get("name"),
                "url": t.get("url"),
            }
        )
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("No targets")
        return 0
    for row in rows:
        print(
            f"{row['index']}. activity_id={row['activity_id'] or '-'}"
            f" | name={row['name'] or '-'} | url={row['url'] or '-'}"
        )
    return 0


def cmd_get(targets: List[Dict[str, Any]], activity_id: str, as_json: bool) -> int:
    idx = find_target_index(targets, activity_id)
    if idx < 0:
        print(f"Target not found: activity_id={activity_id}", file=sys.stderr)
        return 2
    target = targets[idx]
    obj = {
        "index": idx + 1,
        "activity_id": target_activity_id(target),
        "name": target.get("name"),
        "url": target.get("url"),
    }
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(format_target(idx + 1, target))
    return 0


def cmd_add(
    config: Dict[str, Any],
    targets: List[Dict[str, Any]],
    url: str,
    name: Optional[str],
    activity_id: Optional[str],
    upsert: bool,
    as_json: bool,
) -> int:
    aid = parse_activity_id(url, activity_id)
    if not aid:
        print(
            "Cannot parse activity_id from url. Please pass --activity-id explicitly.",
            file=sys.stderr,
        )
        return 2

    idx = find_target_index(targets, aid)
    new_obj = {
        "name": name or f"target-{aid}",
        "url": url,
        "activity_id": aid,
    }
    if idx >= 0:
        if not upsert:
            print(f"Target already exists: activity_id={aid}", file=sys.stderr)
            return 2
        targets[idx] = new_obj
        action = "updated"
    else:
        targets.append(new_obj)
        action = "added"

    if as_json:
        print(
            json.dumps(
                {"action": action, "target": new_obj, "total": len(targets)},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"{action.upper()}: activity_id={aid} | name={new_obj['name']}")
    return 0


def cmd_update(
    targets: List[Dict[str, Any]],
    activity_id: str,
    name: Optional[str],
    url: Optional[str],
    new_activity_id: Optional[str],
    as_json: bool,
) -> int:
    idx = find_target_index(targets, activity_id)
    if idx < 0:
        print(f"Target not found: activity_id={activity_id}", file=sys.stderr)
        return 2

    if name is None and url is None and new_activity_id is None:
        print("No update fields provided.", file=sys.stderr)
        return 2

    cur = dict(targets[idx])
    final_url = url if url is not None else str(cur.get("url", ""))
    parsed_from_url = parse_activity_id(final_url)
    final_activity_id = (
        str(new_activity_id).strip()
        if new_activity_id
        else (parsed_from_url or target_activity_id(cur) or activity_id)
    )

    if final_activity_id != activity_id:
        existing_idx = find_target_index(targets, final_activity_id)
        if existing_idx >= 0 and existing_idx != idx:
            print(
                f"Cannot update: target with activity_id={final_activity_id} already exists.",
                file=sys.stderr,
            )
            return 2

    if name is not None:
        cur["name"] = name
    if url is not None:
        cur["url"] = url
    cur["activity_id"] = final_activity_id
    targets[idx] = cur

    out = {
        "action": "updated",
        "old_activity_id": activity_id,
        "target": {
            "index": idx + 1,
            "activity_id": target_activity_id(cur),
            "name": cur.get("name"),
            "url": cur.get("url"),
        },
    }
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(
            "UPDATED: "
            f"old_activity_id={activity_id} -> activity_id={out['target']['activity_id']} "
            f"| name={out['target']['name']}"
        )
    return 0


def cmd_remove(targets: List[Dict[str, Any]], activity_id: str, as_json: bool) -> int:
    idx = find_target_index(targets, activity_id)
    if idx < 0:
        print(f"Target not found: activity_id={activity_id}", file=sys.stderr)
        return 2
    removed = targets.pop(idx)
    out = {
        "action": "removed",
        "target": {
            "activity_id": target_activity_id(removed),
            "name": removed.get("name"),
            "url": removed.get("url"),
        },
        "total": len(targets),
    }
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"REMOVED: activity_id={out['target']['activity_id']} | name={out['target']['name']}")
    return 0


def build_parser(default_config: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage dzdp monitor targets in config.json")
    parser.add_argument("--config", default=default_config, help="Path to config.json")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="List all targets")
    list_p.add_argument("--json", action="store_true", help="Output JSON")

    get_p = sub.add_parser("get", help="Get one target by activity_id")
    get_p.add_argument("--activity-id", required=True)
    get_p.add_argument("--json", action="store_true", help="Output JSON")

    add_p = sub.add_parser("add", help="Add a target")
    add_p.add_argument("--url", required=True)
    add_p.add_argument("--name")
    add_p.add_argument("--activity-id")
    add_p.add_argument("--upsert", action="store_true", help="Update if exists")
    add_p.add_argument("--json", action="store_true", help="Output JSON")

    upd_p = sub.add_parser("update", help="Update a target by activity_id")
    upd_p.add_argument("--activity-id", required=True, help="Existing activity_id")
    upd_p.add_argument("--name")
    upd_p.add_argument("--url")
    upd_p.add_argument("--new-activity-id")
    upd_p.add_argument("--json", action="store_true", help="Output JSON")

    rm_p = sub.add_parser("remove", help="Remove a target by activity_id")
    rm_p.add_argument("--activity-id", required=True)
    rm_p.add_argument("--json", action="store_true", help="Output JSON")

    return parser


def main() -> int:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_config = os.path.abspath(os.path.join(script_dir, "../../../config.json"))
    parser = build_parser(default_config)
    args = parser.parse_args()
    as_json = bool(getattr(args, "json", False))

    config = load_config(args.config)
    targets = ensure_targets(config)

    if args.command == "list":
        return cmd_list(targets, as_json)

    if args.command == "get":
        return cmd_get(targets, args.activity_id, as_json)

    # Write operations below
    rc = 0
    if args.command == "add":
        rc = cmd_add(
            config=config,
            targets=targets,
            url=args.url,
            name=args.name,
            activity_id=args.activity_id,
            upsert=bool(args.upsert),
            as_json=as_json,
        )
    elif args.command == "update":
        rc = cmd_update(
            targets=targets,
            activity_id=args.activity_id,
            name=args.name,
            url=args.url,
            new_activity_id=args.new_activity_id,
            as_json=as_json,
        )
    elif args.command == "remove":
        rc = cmd_remove(targets, args.activity_id, as_json)
    else:
        print(f"Unsupported command: {args.command}", file=sys.stderr)
        return 2

    if rc == 0:
        save_config(args.config, config)
    return rc


if __name__ == "__main__":
    sys.exit(main())
