# Conversation Flow Reference

## Overview

Conversation issues are tasks without an active project that use a comment-based back-and-forth workflow. Instead of the standard plan→execute→PR pipeline, the daemon reads the issue description + comments, determines what action to take, and responds via comments.

## Inputs

- `config` — loaded per `references/config.md`
- `issue_id` — Linear issue ID to process

## Steps

### 1. Fetch Context

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_issue.py <issue_id>
```

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <issue_id>
```

### 2. Identify Unprocessed Input

Find comments that need a response:
- Sort comments by `created_at` ascending
- Find the last comment tagged `**[Conversation]**` from the operator (config `operator.id`)
- All comments after that point from non-operator users are **unprocessed input**
- If no `**[Conversation]**` comment exists, the issue description + all non-operator comments are unprocessed

### 3. Analyze and Determine Action

Read the full conversation context (description + all comments in order) and determine what the user is asking for. Match against available **abilities**:

| Ability | Trigger | Action |
|---------|---------|--------|
| `create-project` | User wants to start a new project (code repo + Linear project) | Follow `references/project-setup-flow.md` |
| `create-issues` | User wants to create issues in an existing project | Create issues via `tm_save_issue.py` |
| `research` | User asks a question, wants analysis, or needs exploration | Research and respond with findings |
| `close` | User says "done", "thanks", or conversation is resolved | Close the issue |
| `respond` | General conversation — ask clarifying questions, provide status, etc. | Post a response comment |

### 4. Execute the Ability

#### create-project

1. Extract project details from the conversation (name, description, language/framework).
2. Follow `references/project-setup-flow.md` to create the project end-to-end.
3. Post a `**[Conversation]**` comment summarizing what was created:
   ```
   **[Conversation]** Project created:
   - Linear project: <name> (<project-id>)
   - Repository: <repo-url>
   - Local path: <local-path>
   - Config updated

   The project is now active and ready for issues.
   ```
4. If details are missing, post a `**[Conversation]**` comment asking for them:
   ```
   **[Conversation]** I'd like to set up a new project. I need a few details:
   - **Project name**: What should the project be called?
   - **Description**: Brief description of the project
   - **Visibility**: Public or private repository?

   Reply with these details and I'll create everything.
   ```

#### create-issues

1. Parse the requested issues from the conversation.
2. Validate the target project exists in config.
3. Create each issue via `tm_save_issue.py`.
4. Post a `**[Conversation]**` comment listing what was created.

#### research

1. Analyze the question.
2. If the question references a codebase, use available tools to explore.
3. Post a `**[Conversation]**` comment with findings.

#### close

1. Post a `**[Conversation]**` comment:
   ```
   **[Conversation]** Closing this conversation. Summary: <brief summary of what was accomplished>
   ```
2. Set status to Done:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <issue-id> \
     --state "Done"
   ```

#### respond

1. Post a `**[Conversation]**` comment with the response.
2. Leave the issue in its current state (In Progress or Todo).

### 5. Post-Action

After executing an ability:
- If the conversation is complete (ability was `close`), the issue moves to Done. Stop.
- If waiting for user input, leave the issue In Progress. Stop.
- If an ability failed, post a `**[Conversation]**` comment explaining the error and leave In Progress.

## Notes

- Always tag responses with `**[Conversation]**` so the daemon can identify its own messages.
- The daemon only processes conversation issues when all project work is done (Phase 5 in selector).
- If the issue has a project assigned (even one not in active config), treat it as a conversation issue — the user may be asking to set it up.
