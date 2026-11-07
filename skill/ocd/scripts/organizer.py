#!/usr/bin/env python3
"""Build and journal sidebar moves for OCD."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def key(item):
    if "key" in item:
        return item["key"]
    if "projectKind" in item:
        return "project:" + item["projectId"]
    return f"{item['kind']}:{item.get('hostId', 'local') if item['kind'] == 'codex' else ''}:{item['id']}"


def placements(snapshot):
    result = {}
    aliases = snapshot.get("clientThreadAliases", {})
    # The desktop can expose a temporary client ID for the active chat.
    # Resolve only its identity mapping; never write application state.
    if not aliases and any(
        "client-new-thread:" in k
        for s in snapshot["sections"]
        for k in s.get("itemKeys", [])
    ):
        try:
            app = read(Path.home() / ".codex" / ".codex-global-state.json")
            aliases = app.get("electron-persisted-atom-state", {}).get(
                "client-thread-bindings-v1", {}
            )
        except (OSError, ValueError):
            aliases = {}
    for section in snapshot["sections"]:
        for k in section.get("itemKeys", []):
            if ":client-new-thread:" in k:
                prefix, client = k.split(":client-new-thread:", 1)
                canonical = aliases.get("client-new-thread:" + client)
                if isinstance(canonical, str):
                    k = prefix + ":" + canonical
            # A provisional active chat can appear in default and custom lists.
            if k not in result or section["sectionId"] not in ("chats", "threads"):
                result[k] = section["sectionId"]
    return result


def sidebar_key(item):
    if "sidebarKey" in item:
        return item["sidebarKey"]
    if "projectKind" in item:
        return (
            f"codex:project:{item['projectId']}"
            if item["projectKind"] != "chatgpt"
            else f"chatgpt:project:{item['projectId']}"
        )
    if item["kind"] == "codex":
        return f"codex:thread:{item.get('hostId', 'local')}:{item['id']}"
    return f"chatgpt:conversation:{item['id']}"


def inventory(snapshot):
    return {
        key(x): x
        for x in snapshot.get("threads", [])
        + snapshot.get("pinnedThreads", [])
        + snapshot.get("projects", [])
    }


def plan(snapshot, assignment, state=None):
    state = state or {"managed": {}}
    items = inventory(snapshot)
    existing = placements(snapshot)
    names = assignment["sections"]
    if len(names) != len(set(names)) or not all(
        isinstance(n, str) and n.strip() for n in names
    ):
        raise ValueError("Section names must be unique and nonempty")
    operations, skipped = [], []
    seen = set()
    for a in assignment["assignments"]:
        k = a["key"]
        if k in seen:
            raise ValueError("Duplicate assignment: " + k)
        seen.add(k)
        if k not in items or a["section"] not in names:
            raise ValueError("Unknown item or section: " + k)
        item = items[k]
        current = existing.get(sidebar_key(item))
        previous = state.get("managed", {}).get(k)
        # Keep pins and user moves; never pull children out of their existing project.
        reason = None
        if current == "pinned" or item.get("pinned"):
            reason = "Pinned"
        elif a.get("locked") or k in state.get("locks", []):
            reason = "Locked"
        elif previous and current != previous["sectionId"]:
            reason = "Manually moved since last run"
        elif not previous and current and current not in ("threads", "chats"):
            reason = "Existing custom placement"
        elif item.get("projectId") and "projectKind" not in item:
            reason = "Kept inside project"
        elif a.get("confidence", 0) < 0.8:
            reason = "Needs review"
        if reason:
            skipped.append({"key": k, "reason": reason})
            continue
        op = {
            "key": k,
            "title": item.get("title", item.get("label")),
            "section": a["section"],
            "beforeSectionId": current,
            "reason": a["reason"],
            "confidence": a["confidence"],
        }
        if "move" in item:
            move = item["move"]
            op["beforeDestination"] = None if current == "chats" else current
            op.update(
                tool=move.get("tool"),
                args=dict(move.get("args", {})),
                sectionArgument=move.get("sectionArgument", "sectionId"),
            )
        elif "projectKind" in item:
            op.update(
                tool="move_project_to_sidebar_section",
                args={"projectId": item["projectId"]},
            )
        elif item["kind"] in ("codex", "chatgpt"):
            op.update(
                tool="move_thread_to_sidebar_section",
                args={"threadId": item["id"], "source": item["kind"]},
            )
            if item["kind"] == "codex":
                op["args"]["hostId"] = item.get("hostId", "local")
        if "tool" not in op:
            raise ValueError("Unknown provider: supply an explicit move mapping")
        operations.append(op)
    return {
        "version": 1,
        "snapshotHash": hashlib.sha256(
            json.dumps(snapshot, sort_keys=True).encode()
        ).hexdigest(),
        "sections": names,
        "operations": operations,
        "skipped": skipped,
        "beforeSectionOrder": [s["sectionId"] for s in snapshot["sections"]],
    }


def resolve(proposal, section_ids, snapshot):
    current = placements(snapshot)
    items = inventory(snapshot)
    operations = []
    for op in proposal["operations"]:
        if op["section"] not in section_ids:
            raise ValueError("Unresolved section: " + op["section"])
        dest = section_ids[op["section"]]
        actual = current.get(sidebar_key(items[op["key"]]))
        if actual == dest:
            continue
        if not op.get("tool"):
            raise ValueError(
                "No move capability; use the report command for a manual plan"
            )
        if actual != op["beforeSectionId"]:
            raise ValueError("Placement changed since preview: " + op["key"])
        operations.append(
            {
                **op,
                "afterSectionId": dest,
                "args": {**op["args"], op.get("sectionArgument", "sectionId"): dest},
            }
        )
    return {
        **proposal,
        "operations": operations,
        "sectionIds": section_ids,
        "completed": [],
        "failures": [],
    }


def record(journal, index, result):
    if not isinstance(index, int) or index < 0 or index >= len(journal["operations"]):
        raise ValueError("Invalid operation index")
    error = result.get("isError", False)
    journal["failures"] = [x for x in journal["failures"] if x["index"] != index]
    if error:
        journal["failures"].append({"index": index, "result": result})
    elif index not in journal["completed"]:
        journal["completed"].append(index)
    return journal


def undo(journal, current):
    places = placements(current)
    items = inventory(current)
    ops, skipped = [], []
    for index in reversed(journal["completed"]):
        op = journal["operations"][index]
        if (
            op["key"] not in items
            or places.get(sidebar_key(items[op["key"]])) != op["afterSectionId"]
        ):
            skipped.append(
                {"key": op["key"], "reason": "Missing or moved after organization"}
            )
            continue
        ops.append(
            {
                "key": op["key"],
                "tool": op["tool"],
                "args": {
                    **op["args"],
                    op.get("sectionArgument", "sectionId"): op.get(
                        "beforeDestination", op["beforeSectionId"]
                    ),
                },
            }
        )
    return {
        "operations": ops,
        "skipped": skipped,
        "note": "Only remove organizer-created sections after verifying they are empty. Restore section order from the before snapshot.",
    }


def normalize_export(export):
    """Translate an app's exported chats and tool mapping into planner input."""
    provider = export["app"]
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("app must be a nonempty provider identifier")
    sections = [{"sectionId": "chats", "name": "Unsorted", "itemKeys": []}]
    known_sections = {"chats": sections[0]}
    for group in export.get("groups", []):
        if group["id"] in known_sections:
            raise ValueError("Duplicate group: " + group["id"])
        section = {"sectionId": group["id"], "name": group["name"], "itemKeys": []}
        known_sections[group["id"]] = section
        sections.append(section)
    items, seen = [], set()
    for chat in export["items"]:
        identity = chat["id"]
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("Item IDs must be unique nonempty strings")
        seen.add(identity)
        group = chat.get("groupId") or "chats"
        if group not in known_sections:
            raise ValueError("Unknown group: " + group)
        mapping = export.get("move", {})
        if mapping and (
            not mapping.get("tool")
            or not mapping.get("itemArgument")
            or not mapping.get("sectionArgument")
        ):
            raise ValueError("move requires tool, itemArgument and sectionArgument")
        args = dict(mapping.get("args", {}))
        if mapping:
            args[mapping["itemArgument"]] = identity
        item = {
            "id": identity,
            "key": provider + ":" + identity,
            "kind": provider,
            "sidebarKey": provider + ":" + identity,
            "title": chat["title"],
            "summary": chat.get("summary"),
            "updatedAt": chat.get("updatedAt"),
            "projectId": chat.get("projectId"),
            "pinned": chat.get("pinned", False),
            "move": {
                "tool": mapping.get("tool"),
                "args": args,
                "sectionArgument": mapping.get("sectionArgument", "sectionId"),
            },
        }
        known_sections[group]["itemKeys"].append(item["sidebarKey"])
        items.append(item)
    return {
        "schemaVersion": 1,
        "app": provider,
        "sections": sections,
        "threads": items,
        "projects": [],
        "pinnedThreads": [],
    }


def report(proposal):
    """Render a plan without requiring a writable app integration."""

    def plain(value):
        return str(value).replace("\n", " ").replace("\r", " ")

    lines = [
        "# OCD organization plan",
        "",
        "Proposed layout; no app changes have been made.",
        "",
    ]
    for section in proposal["sections"]:
        lines.extend(["## " + plain(section), ""])
        for op in proposal["operations"]:
            if op["section"] == section:
                lines.append("- " + plain(op["title"]) + " — " + plain(op["reason"]))
        lines.append("")
    if proposal["skipped"]:
        lines.extend(["## Preserved or awaiting review", ""])
        lines.extend(
            "- " + plain(op["key"]) + ": " + plain(op["reason"])
            for op in proposal["skipped"]
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    plan_parser = commands.add_parser("plan", help="Build a proposed set of moves")
    plan_parser.add_argument("snapshot")
    plan_parser.add_argument("assignments")
    plan_parser.add_argument("output")
    plan_parser.add_argument("--state")

    resolve_parser = commands.add_parser(
        "resolve", help="Resolve section names and check for stale placements"
    )
    resolve_parser.add_argument("plan")
    resolve_parser.add_argument("sections")
    resolve_parser.add_argument("snapshot")
    resolve_parser.add_argument("output")

    record_parser = commands.add_parser(
        "record", help="Save one app tool result to the journal"
    )
    record_parser.add_argument("journal")
    record_parser.add_argument("index", type=int)
    record_parser.add_argument("result")

    undo_parser = commands.add_parser(
        "undo", help="Build restoration moves from a journal"
    )
    undo_parser.add_argument("journal")
    undo_parser.add_argument("snapshot")
    undo_parser.add_argument("output")

    normalize_parser = commands.add_parser(
        "normalize", help="Import an app-neutral chat export"
    )
    normalize_parser.add_argument("export")
    normalize_parser.add_argument("output")
    report_parser = commands.add_parser(
        "report", help="Write a Markdown layout for manual organization"
    )
    report_parser.add_argument("plan")
    report_parser.add_argument("output")

    args = parser.parse_args()
    if args.command == "normalize":
        write(args.output, normalize_export(read(args.export)))
        return
    if args.command == "report":
        Path(args.output).write_text(report(read(args.plan)), encoding="utf-8")
        return
    if args.command == "plan":
        state = read(args.state) if args.state else None
        result = plan(read(args.snapshot), read(args.assignments), state)
    elif args.command == "resolve":
        result = resolve(read(args.plan), read(args.sections), read(args.snapshot))
    elif args.command == "record":
        result = record(read(args.journal), args.index, read(args.result))
        write(args.journal, result)
        return
    else:
        result = undo(read(args.journal), read(args.snapshot))

    write(args.output, result)
    moves = len(result.get("operations", []))
    skipped = len(result.get("skipped", []))
    print(f"{moves} operations; {skipped} preserved/review items")


if __name__ == "__main__":
    main()
