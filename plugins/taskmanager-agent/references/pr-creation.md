# PR Creation Reference

## Steps

1. Parse the repo URL from config for the current project.
2. Call the platform-agnostic PR creation script. Platform detection is handled automatically.

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/create_pr.py \
  --repo-url <url> \
  --branch <branch> \
  --title "<key>: <title>" \
  --body "Resolves [<key>](<issue-url>)\n\n<summary>"
```

The script auto-detects the git hosting platform (Forgejo, GitHub, etc.) from the repo URL and delegates to the appropriate backend.

---

### Notes

- Default base branch is `main`.
- `<key>` is the Linear issue identifier (e.g. `ENG-42`).
- `<issue-url>` is the full Linear URL for the issue.
- `<summary>` is a brief description of the changes made.
- Platform detection is based on the hostname in the repo URL.
