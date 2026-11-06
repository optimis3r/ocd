#!/usr/bin/env python3
"""Install the skill without copying local chat history."""

import argparse
import os
from pathlib import Path
import shutil


def install(source, target, data_dir=None):
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "data-location.txt"),
    )

    location = target / "data-location.txt"
    if data_dir is not None:
        location.write_text(
            str(data_dir.expanduser().resolve()) + "\n", encoding="utf-8"
        )
    elif not location.exists():
        data_home = Path(
            os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
        )
        location.write_text(
            str(data_home / "codex-chat-organizer") + "\n", encoding="utf-8"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, help="Location for private snapshots and journals"
    )
    args = parser.parse_args()
    source = Path(__file__).resolve().parent / "skill" / "codex-chat-organizer"
    target = Path.home() / ".codex" / "skills" / source.name
    install(source, target, args.data_dir)
    print(f"Installed Chat Organizer at {target}")


if __name__ == "__main__":
    main()
