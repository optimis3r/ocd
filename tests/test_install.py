import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

INSTALLER_PATH = Path(__file__).resolve().parents[1] / "install.py"
spec = importlib.util.spec_from_file_location("installer", INSTALLER_PATH)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallationTests(unittest.TestCase):
    def test_update_preserves_existing_data_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "installed"
            source.mkdir()
            target.mkdir()
            (source / "SKILL.md").write_text("updated skill")
            (source / "data-location.txt").write_text("another machine")
            (target / "data-location.txt").write_text("/private/history\n")

            installer.install(source, target)

            self.assertEqual((target / "SKILL.md").read_text(), "updated skill")
            self.assertEqual(
                (target / "data-location.txt").read_text(), "/private/history\n"
            )

    def test_new_install_uses_external_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "repo" / "skill"
            target = root / "installed"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("skill")

            with patch.dict(os.environ, {"XDG_DATA_HOME": str(root / "private")}):
                installer.install(source, target)

            expected = root / "private" / "ocd"
            self.assertEqual(
                (target / "data-location.txt").read_text().strip(), str(expected)
            )
            self.assertFalse((source.parent / "data").exists())

    def test_explicit_data_directory_does_not_move_old_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "installed"
            old_data = root / "old-history"
            new_data = root / "new-history"
            source.mkdir()
            old_data.mkdir()
            (old_data / "snapshot.json").write_text("{}")

            installer.install(source, target, new_data)

            self.assertEqual(
                (target / "data-location.txt").read_text().strip(), str(new_data)
            )
            self.assertTrue((old_data / "snapshot.json").exists())
            self.assertFalse(new_data.exists())


if __name__ == "__main__":
    unittest.main()
