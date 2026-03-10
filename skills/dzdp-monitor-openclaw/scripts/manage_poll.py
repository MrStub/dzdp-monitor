#!/usr/bin/env python3
import argparse
import json
import os
import sys
from typing import Any, Dict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app_config import MIN_INTERVAL_SECONDS, ensure_poll, get_interval_seconds, load_config, save_config  # noqa: E402


def cmd_get(config: Dict[str, Any], as_json: bool) -> int:
    interval = get_interval_seconds(config)
    payload = {"interval_seconds": interval, "min_interval_seconds": MIN_INTERVAL_SECONDS}
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"interval_seconds={interval}")
    return 0


def cmd_set(config: Dict[str, Any], seconds: int, as_json: bool) -> int:
    if seconds < MIN_INTERVAL_SECONDS:
        print(f"interval_seconds must be >= {MIN_INTERVAL_SECONDS}", file=sys.stderr)
        return 2

    poll = ensure_poll(config)
    old_value = get_interval_seconds(config)
    poll["interval_seconds"] = int(seconds)
    payload = {
        "action": "updated",
        "old_interval_seconds": old_value,
        "interval_seconds": int(seconds),
        "min_interval_seconds": MIN_INTERVAL_SECONDS,
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"UPDATED: interval_seconds={old_value} -> {int(seconds)}")
    return 0


def build_parser(default_config: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage dzdp monitor poll interval in config.json")
    parser.add_argument("--config", default=default_config, help="Path to config.json")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    sub = parser.add_subparsers(dest="command", required=True)

    get_p = sub.add_parser("get", help="Get current poll interval")
    get_p.add_argument("--json", action="store_true", help="Output JSON")

    set_p = sub.add_parser("set", help="Set poll interval in seconds")
    set_p.add_argument("--seconds", required=True, type=int)
    set_p.add_argument("--json", action="store_true", help="Output JSON")

    return parser


def main() -> int:
    default_config = os.path.abspath(os.path.join(SCRIPT_DIR, "../../../config.json"))
    parser = build_parser(default_config)
    args = parser.parse_args()
    as_json = bool(getattr(args, "json", False))

    config = load_config(args.config)

    if args.command == "get":
        return cmd_get(config, as_json)

    if args.command == "set":
        rc = cmd_set(config, args.seconds, as_json)
        if rc == 0:
            save_config(args.config, config)
        return rc

    print(f"Unsupported command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
