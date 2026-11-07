import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "organizer",
    Path(__file__).resolve().parents[1] / "skill/ocd/scripts/organizer.py",
)
organizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(organizer)


class Transactions(unittest.TestCase):
    def snapshot(self, section="chats", project=None):
        return {
            "sections": [{"sectionId": section, "itemKeys": ["codex:thread:local:a"]}],
            "threads": [
                {
                    "id": "a",
                    "kind": "codex",
                    "hostId": "local",
                    "title": "A",
                    "projectId": project,
                }
            ],
            "projects": [],
        }

    def assignment(self, confidence=1):
        return {
            "sections": ["Learning"],
            "assignments": [
                {
                    "key": "codex:local:a",
                    "section": "Learning",
                    "confidence": confidence,
                    "reason": "Coursework",
                }
            ],
        }

    def test_protect_pins_projects_and_uncertainty(self):
        for snapshot, confidence in [
            (self.snapshot("pinned"), 1),
            (self.snapshot(project="p"), 1),
            (self.snapshot(), 0.6),
            (self.snapshot("custom"), 1),
        ]:
            self.assertEqual(
                organizer.plan(snapshot, self.assignment(confidence))["operations"], []
            )

    def test_manual_moves_survive_refresh(self):
        state = {"managed": {"codex:local:a": {"sectionId": "old"}}}
        self.assertEqual(
            organizer.plan(self.snapshot("new"), self.assignment(), state)[
                "operations"
            ],
            [],
        )

    def test_idempotency_and_stale_plan(self):
        s = self.snapshot()
        p = organizer.plan(s, self.assignment())
        journal = organizer.resolve(p, {"Learning": "dest"}, s)
        self.assertEqual(len(journal["operations"]), 1)
        self.assertEqual(
            organizer.resolve(p, {"Learning": "dest"}, self.snapshot("dest"))[
                "operations"
            ],
            [],
        )
        with self.assertRaises(ValueError):
            organizer.resolve(p, {"Learning": "dest"}, self.snapshot("other"))

    def test_only_successful_unchanged_moves_are_undone(self):
        s = self.snapshot()
        j = organizer.resolve(
            organizer.plan(s, self.assignment()), {"Learning": "dest"}, s
        )
        organizer.record(j, 0, {"isError": True})
        self.assertEqual(organizer.undo(j, self.snapshot("dest"))["operations"], [])
        organizer.record(j, 0, {"isError": False})
        organizer.record(j, 0, {"isError": False})
        self.assertEqual(len(j["completed"]), 1)
        self.assertEqual(
            organizer.undo(j, self.snapshot("dest"))["operations"][0]["args"][
                "sectionId"
            ],
            "chats",
        )
        self.assertEqual(
            organizer.undo(j, self.snapshot("user-choice"))["operations"], []
        )
        self.assertEqual(organizer.undo(j, self.snapshot("chats"))["operations"], [])

    def test_temporary_client_identity(self):
        s = self.snapshot("dest")
        s["sections"][0]["itemKeys"] = ["codex:thread:local:client-new-thread:tmp"]
        s["sections"].append(
            {"sectionId": "chats", "itemKeys": ["codex:thread:local:a"]}
        )
        s["clientThreadAliases"] = {"client-new-thread:tmp": "a"}
        self.assertEqual(organizer.placements(s)["codex:thread:local:a"], "dest")
        p = organizer.plan(self.snapshot(), self.assignment())
        self.assertEqual(
            organizer.resolve(p, {"Learning": "dest"}, s)["operations"], []
        )

    def test_atomic_round_trip(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "nested/state.json"
            organizer.write(p, {"x": "✓"})
            self.assertEqual(organizer.read(p), {"x": "✓"})

    def test_invalid_assignment_rejected(self):
        a = self.assignment()
        a["assignments"] *= 2
        with self.assertRaises(ValueError):
            organizer.plan(self.snapshot(), a)


if __name__ == "__main__":
    unittest.main()
