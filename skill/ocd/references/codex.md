# Codex desktop integration

This integration is optional. It is used only when the target is Codex/ChatGPT history and the native desktop tools are available.

Discover `list_threads`, `list_projects`, `read_thread`, `create_sidebar_section`, `move_thread_to_sidebar_section`, `move_project_to_sidebar_section`, and `reorder_sidebar_sections`.

Collect sections, sidebar preferences and pinned threads from recent `list_threads`. Paginate history separately for `codex` and `chatgpt` until nextCursor is empty. Collect projects with `list_projects`. Preserve host IDs. Deduplicate chats by source, host and ID. Merge them into `{sections, sidebarPreferences, pinnedThreads, threads, projects, capturedAt}`.

This native snapshot can go directly into `plan`. Its historical keys remain supported:

- `codex:<hostId>:<threadId>`
- `chatgpt::<conversationId>`
- `project:<projectId>`

The planner emits the native sidebar move tools and their arguments. Project children remain in their existing project. Reordering sections must retain all preexisting custom sections.

Codex sometimes exposes an active chat under a temporary client ID. The helper accepts a snapshot `clientThreadAliases` mapping and can fall back to reading the local Codex identity map. This fallback is read-only and only used for native temporary IDs. Generic exports never need it.

For existing installations, preserve `data-location.txt` and the existing state/journals. Renaming the skill must not reset organization history.
