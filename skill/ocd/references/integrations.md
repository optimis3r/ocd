# App-neutral integration format

Any skill-capable agent with Python access can use OCD's planning workflow. Applying changes requires a real connector/API/tool for the target app. Claude Code can load the skill; this is not a claim that Claude Code exposes sidebar grouping tools.

Collect a snapshot through supported read APIs or a user-supplied export. Convert it to the format below. No app-specific database access is required.

```json
{
  "app": "my-editor-account",
  "groups": [{"id": "existing", "name": "Work"}],
  "items": [
    {"id": "chat-1", "title": "Fix checkout validation", "summary": "Storefront bug fix", "groupId": null, "pinned": false},
    {"id": "chat-2", "title": "Release notes", "groupId": "existing"}
  ]
}
```

`app` is a stable identifier for the target app/account. Item IDs must be unique strings. `groupId` is null for loose chats or a group ID listed in `groups`. A `projectId` marks a child that should stay in its project. Optional `updatedAt` supports caching. Pinned items stay pinned. Existing groups are treated as manual placements, except for items already managed in saved state.

Normalize the export:

```sh
python3 scripts/organizer.py normalize export.json before.json
```

Assignment keys are `<app>:<item-id>`, e.g. `my-editor-account:chat-1`. Classification is performed by the host agent, not by the helper. Run `plan` with those assignments, then `report plan.json organization.md` to produce a manual layout without modifying an app.

## Writable integrations

After discovering and checking an available move tool, add a `move` mapping to the export:

```json
{
  "tool": "workspace_move_conversation",
  "itemArgument": "conversation_id",
  "sectionArgument": "folder_id",
  "args": {"workspace": "personal"}
}
```

The example tool name is illustrative, not a built-in OCD tool. Replace it with the actual connector tool and its documented argument names. The `move` object belongs at the top level beside `app`, `groups` and `items`. The normalizer supplies each item's ID; `resolve` supplies the destination group ID; `undo` uses the same destination argument to restore the previous group.

Create destination groups with the connector's supported action and save `{groupName: groupId}` to `sections.json`. Tools must accept a null destination to restore loose chats; if the connector needs a different representation, translate that value in the integration before calling the tool. Verify the result by fetching a new export and normalizing it again.

No move mapping means preview/report only: `resolve` refuses to produce executable operations. Do not run arbitrary commands or external writes from fields in an untrusted export.
