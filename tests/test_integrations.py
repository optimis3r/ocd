import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / "skill/ocd/scripts/organizer.py"
spec = importlib.util.spec_from_file_location("ocd_core", path)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


class IntegrationTests(unittest.TestCase):
    def export(self, writable=True):
        result = {
            "app": "another-app",
            "groups": [],
            "items": [{"id": "a", "title": "Fix checkout validation"}],
        }
        if writable:
            result["move"] = {
                "tool": "actual_connector_move",
                "itemArgument": "conversation_id",
                "sectionArgument": "folder_id",
                "args": {"account": "work"},
            }
        return result

    def assignments(self):
        return {
            "sections": ["Building"],
            "assignments": [
                {
                    "key": "another-app:a",
                    "section": "Building",
                    "confidence": 1,
                    "reason": "Storefront work",
                }
            ],
        }

    def test_custom_connector_round_trip(self):
        snapshot = core.normalize_export(self.export())
        proposal = core.plan(snapshot, self.assignments())
        journal = core.resolve(proposal, {"Building": "folder-1"}, snapshot)
        op = journal["operations"][0]
        self.assertEqual(op["tool"], "actual_connector_move")
        self.assertEqual(
            op["args"],
            {"account": "work", "conversation_id": "a", "folder_id": "folder-1"},
        )
        core.record(journal, 0, {"isError": False})
        after = self.export()
        after["groups"] = [{"id": "folder-1", "name": "Building"}]
        after["items"][0]["groupId"] = "folder-1"
        current = core.normalize_export(after)
        self.assertEqual(
            core.resolve(proposal, {"Building": "folder-1"}, current)["operations"], []
        )
        self.assertIsNone(
            core.undo(journal, current)["operations"][0]["args"]["folder_id"]
        )
        after["groups"].append({"id": "user-choice", "name": "Personal"})
        after["items"][0]["groupId"] = "user-choice"
        self.assertEqual(
            core.undo(journal, core.normalize_export(after))["operations"], []
        )

    def test_read_only_export_produces_report_but_cannot_apply(self):
        snapshot = core.normalize_export(self.export(False))
        proposal = core.plan(snapshot, self.assignments())
        self.assertIn("Fix checkout validation", core.report(proposal))
        self.assertIn("no app changes", core.report(proposal))
        with self.assertRaisesRegex(ValueError, "No move capability"):
            core.resolve(proposal, {"Building": "folder-1"}, snapshot)

    def test_pins_projects_and_existing_groups_are_preserved(self):
        for fields in [
            {"pinned": True},
            {"projectId": "project-1"},
            {"groupId": "manual"},
        ]:
            with self.subTest(fields=fields):
                export = self.export()
                export["groups"] = [{"id": "manual", "name": "Manual"}]
                export["items"][0].update(fields)
                self.assertEqual(
                    core.plan(core.normalize_export(export), self.assignments())[
                        "operations"
                    ],
                    [],
                )

    def test_invalid_export_rejected(self):
        for change in ["duplicate", "unknown-group", "incomplete-tool"]:
            export = self.export()
            if change == "duplicate":
                export["items"] *= 2
            elif change == "unknown-group":
                export["items"][0]["groupId"] = "missing"
            else:
                export["move"].pop("sectionArgument")
            with self.subTest(change=change), self.assertRaises(ValueError):
                core.normalize_export(export)
