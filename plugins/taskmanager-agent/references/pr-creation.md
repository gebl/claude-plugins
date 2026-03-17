# PR Creation Reference

## Steps

1. Parse the repo URL from config for the current project.
2. Inspect the hostname to determine the platform.

---

### Forgejo

If the hostname contains `"forgejo"` or matches `forgejo.bishop.landq.net`:

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/create_forgejo_pr.py \
  --repo-url <url> \
  --branch <branch> \
  --title "<key>: <title>" \
  --body "Resolves [<key>](<issue-url>)\n\n<summary>"
```

---

### GitHub

If the hostname contains `"github.com"`:

```bash
gh pr create \
  --title "<key>: <title>" \
  --body "Resolves [<key>](<issue-url>)\n\n<summary>" \
  --head <branch> \
  --base main
```

---

### Notes

- Default base branch is `main`.
- `<key>` is the Linear issue identifier (e.g. `ENG-42`).
- `<issue-url>` is the full Linear URL for the issue.
- `<summary>` is a brief description of the changes made.
