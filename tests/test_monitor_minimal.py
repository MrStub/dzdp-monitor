import os
import sqlite3
import sys
import tempfile
import unittest

from app_config import add_target, list_targets, update_target
from monitor import StateStore, Target

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "skills", "dzdp-monitor-openclaw", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from manage_targets import build_parser


class MinimalMonitorFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "monitor_state.db")
        self.config = {
            "sqlite_path": self.db_path,
            "notify": {
                "feishu_groups": [
                    {"key": "default", "name": "默认分组", "webhook": ""},
                ],
                "default_group_key": "default",
                "email": {"enabled": False},
            },
            "targets": [],
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_enabled_flag_parameter_path_exists(self) -> None:
        parser = build_parser("/tmp/config.json")

        add_args = parser.parse_args(
            [
                "add",
                "--url",
                "https://example.com/deal?activityId=1001",
                "--disabled",
            ]
        )
        self.assertIs(add_args.enabled, False)

        add_target(
            self.config,
            url=add_args.url,
            name="test-target",
            activity_id=None,
            group_keys_values=None,
            group_key_value="default",
            enabled=add_args.enabled,
            upsert=False,
        )
        rows = list_targets(self.config)
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]["enabled"], False)

        update_args = parser.parse_args(["update", "--index", "1", "--set-enabled"])
        self.assertIs(update_args.set_enabled, True)
        update_target(
            self.config,
            activity_id=None,
            index=1,
            selector_name=None,
            selector_url=None,
            set_name=None,
            set_url=None,
            new_activity_id=None,
            set_group_keys=None,
            set_group_key=None,
            set_enabled=update_args.set_enabled,
        )
        updated_rows = list_targets(self.config)
        self.assertIs(updated_rows[0]["enabled"], True)

    def test_auto_disable_after_five_unavailable_failures(self) -> None:
        add_target(
            self.config,
            url="https://example.com/deal?activityId=2002",
            name="auto-disable-target",
            activity_id=None,
            group_keys_values=None,
            group_key_value="default",
            enabled=True,
            upsert=False,
        )
        target = Target(
            name="auto-disable-target",
            url="https://example.com/deal?activityId=2002",
            activity_id="2002",
            group_keys=["default"],
            enabled=True,
        )
        store = StateStore(self.db_path)
        try:
            for attempt in range(1, 5):
                failure = store.record_unavailable_signal_failure(target, "productBriefInfo is null", threshold=5)
                self.assertFalse(failure.auto_disabled)
                self.assertEqual(failure.consecutive_null_brief_count, attempt)

            fifth = store.record_unavailable_signal_failure(target, "productBriefInfo is null", threshold=5)
            self.assertTrue(fifth.auto_disabled)
            self.assertEqual(fifth.consecutive_null_brief_count, 5)

            row = store.get(target.activity_id)
            self.assertIsNotNone(row)
            self.assertEqual(row["disabled_reason"], "brief_null_or_login_required_auto_disabled")

            conn = sqlite3.connect(self.db_path)
            try:
                enabled = conn.execute(
                    "SELECT enabled FROM monitor_targets WHERE activity_id = ?",
                    (target.activity_id,),
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(enabled, 0)
        finally:
            store.conn.close()


if __name__ == "__main__":
    unittest.main()
