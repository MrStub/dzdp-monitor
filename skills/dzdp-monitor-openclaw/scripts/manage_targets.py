#!/usr/bin/env python3
import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

EPHEMERAL_QUERY_KEYS = {"shareid", "shareId"}


def parse_activity_id(url: str, explicit_activity_id: Optional[str] = None) -> Optional[str]:
    if explicit_activity_id:
        return str(explicit_activity_id).strip()
    parsed = urlparse(url)
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


def target_activity_id(target: Dict[str, Any]) -> Optional[str]:
    return parse_activity_id(str(target.get("url", "")), target.get("activity_id"))


def target_name(target: Dict[str, Any]) -> str:
    return str(target.get("name", "")).strip()


def target_url(target: Dict[str, Any]) -> str:
    return normalize_url(str(target.get("url", "")))


def ensure_targets(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    targets = config.get("targets")
    if not isinstance(targets, list):
        config["targets"] = []
        targets = config["targets"]
    return targets


def normalize_targets_in_place(targets: List[Dict[str, Any]]) -> bool:
    changed = False
    for target in targets:
        normalized_name = target_name(target)
        normalized_url = target_url(target)
        normalized_activity_id = parse_activity_id(normalized_url, target.get("activity_id"))

        if target.get("name") != normalized_name:
            target["name"] = normalized_name
            changed = True
        if target.get("url") != normalized_url:
            target["url"] = normalized_url
            changed = True
        if normalized_activity_id and str(target.get("activity_id", "")).strip() != normalized_activity_id:
            target["activity_id"] = normalized_activity_id
            changed = True
    return changed


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
        return -1, build_not_found_message(
            activity_id=activity_id,
            index=index,
            name=name,
            url=url,
        )

    if index is not None:
        if 1 <= index <= len(targets):
            return index - 1, None
        return -1, build_not_found_message(
            activity_id=activity_id,
            index=index,
            name=name,
            url=url,
        )

    if name:
        matched = find_target_indexes_by_name(targets, name)
        if len(matched) == 1:
            return matched[0], None
        if len(matched) > 1:
            return -1, f"Multiple targets match name={name}. Please use index or activity_id."
        return -1, build_not_found_message(
            activity_id=activity_id,
            index=index,
            name=name,
            url=url,
        )

    if url:
        matched = find_target_indexes_by_url(targets, url)
        if len(matched) == 1:
            return matched[0], None
        if len(matched) > 1:
            return -1, f"Multiple targets match url={normalize_url(url)}. Please use index."
        return -1, build_not_found_message(
            activity_id=activity_id,
            index=index,
            name=name,
            url=url,
        )

    return -1, "One selector is required: --activity-id / --index / --name / --url"


def ensure_name_unique(
    targets: List[Dict[str, Any]],
    name: str,
    *,
    current_index: Optional[int] = None,
) -> Optional[str]:
    matched = find_target_indexes_by_name(targets, name)
    filtered = [idx for idx in matched if current_index is None or idx != current_index]
    if filtered:
        return f"Target name already exists: name={name}"
    return None


def format_target(idx: int, target: Dict[str, Any]) -> str:
    return (
        f"{idx}. activity_id={target_activity_id(target) or '-'}"
        f" | name={target_name(target) or '-'}"
        f" | url={target_url(target) or '-'}"
    )


def cmd_list(targets: List[Dict[str, Any]], as_json: bool) -> int:
    rows = []
    for idx, target in enumerate(targets, start=1):
        rows.append(
            {
                "index": idx,
                "activity_id": target_activity_id(target),
                "name": target_name(target),
                "url": target_url(target),
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


def cmd_get(
    targets: List[Dict[str, Any]],
    *,
    activity_id: Optional[str],
    index: Optional[int],
    name: Optional[str],
    url: Optional[str],
    as_json: bool,
) -> int:
    idx, err = resolve_target_index(
        targets,
        activity_id=activity_id,
        index=index,
        name=name,
        url=url,
    )
    if idx < 0:
        print(err, file=sys.stderr)
        return 2

    target = targets[idx]
    obj = {
        "index": idx + 1,
        "activity_id": target_activity_id(target),
        "name": target_name(target),
        "url": target_url(target),
    }
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(format_target(idx + 1, target))
    return 0


def cmd_add(
    targets: List[Dict[str, Any]],
    *,
    url: str,
    name: Optional[str],
    activity_id: Optional[str],
    upsert: bool,
    as_json: bool,
) -> int:
    normalized_url = normalize_url(url)
    aid = parse_activity_id(normalized_url, activity_id)
    if not aid:
        print(
            "Cannot parse activity_id from url. Please pass --activity-id explicitly.",
            file=sys.stderr,
        )
        return 2

    final_name = str(name or f"target-{aid}").strip()
    if not final_name:
        print("Target name cannot be empty.", file=sys.stderr)
        return 2

    idx = find_target_index(targets, aid)
    name_err = ensure_name_unique(targets, final_name, current_index=idx if idx >= 0 else None)
    if name_err:
        print(name_err, file=sys.stderr)
        return 2

    new_obj = {
        "name": final_name,
        "url": normalized_url,
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

    out = {"action": action, "target": new_obj, "total": len(targets)}
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"{action.upper()}: activity_id={aid} | name={final_name} | url={normalized_url}")
    return 0


def cmd_update(
    targets: List[Dict[str, Any]],
    *,
    activity_id: Optional[str],
    index: Optional[int],
    selector_name: Optional[str],
    selector_url: Optional[str],
    set_name: Optional[str],
    set_url: Optional[str],
    new_activity_id: Optional[str],
    as_json: bool,
) -> int:
    idx, err = resolve_target_index(
        targets,
        activity_id=activity_id,
        index=index,
        name=selector_name,
        url=selector_url,
    )
    if idx < 0:
        print(err, file=sys.stderr)
        return 2

    if set_name is None and set_url is None and new_activity_id is None:
        print("No update fields provided.", file=sys.stderr)
        return 2

    cur = dict(targets[idx])
    current_activity_id = target_activity_id(cur) or ""
    final_url = normalize_url(set_url) if set_url is not None else target_url(cur)
    parsed_from_url = parse_activity_id(final_url)
    final_activity_id = (
        str(new_activity_id).strip()
        if new_activity_id
        else (parsed_from_url or current_activity_id)
    )
    if not final_activity_id:
        print("Cannot determine final activity_id.", file=sys.stderr)
        return 2

    if final_activity_id != current_activity_id:
        existing_idx = find_target_index(targets, final_activity_id)
        if existing_idx >= 0 and existing_idx != idx:
            print(
                f"Cannot update: target with activity_id={final_activity_id} already exists.",
                file=sys.stderr,
            )
            return 2

    if set_name is not None:
        final_name = str(set_name).strip()
        if not final_name:
            print("Target name cannot be empty.", file=sys.stderr)
            return 2
        name_err = ensure_name_unique(targets, final_name, current_index=idx)
        if name_err:
            print(name_err, file=sys.stderr)
            return 2
        cur["name"] = final_name

    if set_url is not None:
        cur["url"] = final_url

    cur["activity_id"] = final_activity_id
    targets[idx] = cur

    out = {
        "action": "updated",
        "old_activity_id": current_activity_id,
        "target": {
            "index": idx + 1,
            "activity_id": target_activity_id(cur),
            "name": target_name(cur),
            "url": target_url(cur),
        },
    }
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(
            "UPDATED: "
            f"old_activity_id={current_activity_id or '-'} -> activity_id={out['target']['activity_id']} "
            f"| name={out['target']['name']} | url={out['target']['url']}"
        )
    return 0


def cmd_remove(
    targets: List[Dict[str, Any]],
    *,
    activity_id: Optional[str],
    index: Optional[int],
    name: Optional[str],
    url: Optional[str],
    as_json: bool,
) -> int:
    idx, err = resolve_target_index(
        targets,
        activity_id=activity_id,
        index=index,
        name=name,
        url=url,
    )
    if idx < 0:
        print(err, file=sys.stderr)
        return 2

    removed = targets.pop(idx)
    out = {
        "action": "removed",
        "target": {
            "index": idx + 1,
            "activity_id": target_activity_id(removed),
            "name": target_name(removed),
            "url": target_url(removed),
        },
        "total": len(targets),
    }
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(
            f"REMOVED: index={out['target']['index']}"
            f" | activity_id={out['target']['activity_id']}"
            f" | name={out['target']['name']}"
        )
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
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_config = os.path.abspath(os.path.join(script_dir, "../../../config.json"))
    parser = build_parser(default_config)
    args = parser.parse_args()
    as_json = bool(getattr(args, "json", False))

    config = load_config(args.config)
    targets = ensure_targets(config)
    normalized_changed = normalize_targets_in_place(targets)

    if args.command == "list":
        rc = cmd_list(targets, as_json)
        if normalized_changed:
            save_config(args.config, config)
        return rc

    if args.command == "get":
        rc = cmd_get(
            targets,
            activity_id=getattr(args, "activity_id", None),
            index=getattr(args, "index", None),
            name=getattr(args, "name", None),
            url=getattr(args, "url", None),
            as_json=as_json,
        )
        if normalized_changed:
            save_config(args.config, config)
        return rc

    rc = 0
    if args.command == "add":
        rc = cmd_add(
            targets,
            url=args.url,
            name=args.name,
            activity_id=args.activity_id,
            upsert=bool(args.upsert),
            as_json=as_json,
        )
    elif args.command == "update":
        rc = cmd_update(
            targets,
            activity_id=getattr(args, "activity_id", None),
            index=getattr(args, "index", None),
            selector_name=getattr(args, "selector_name", None),
            selector_url=getattr(args, "selector_url", None),
            set_name=getattr(args, "set_name", None),
            set_url=getattr(args, "set_url", None),
            new_activity_id=args.new_activity_id,
            as_json=as_json,
        )
    elif args.command == "remove":
        rc = cmd_remove(
            targets,
            activity_id=getattr(args, "activity_id", None),
            index=getattr(args, "index", None),
            name=getattr(args, "name", None),
            url=getattr(args, "url", None),
            as_json=as_json,
        )
    else:
        print(f"Unsupported command: {args.command}", file=sys.stderr)
        return 2

    if rc == 0 or normalized_changed:
        save_config(args.config, config)
    return rc


if __name__ == "__main__":
    sys.exit(main())
