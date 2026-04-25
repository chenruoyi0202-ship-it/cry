# Project preferences

## Deployment

- All code changes for this repo must be **auto-deployed** to the live GitHub Pages site (https://chenruoyi0202-ship-it.github.io/cry/) without asking the user first.
- Default workflow after making changes: commit → push → open PR → mark ready (not draft) → merge to `main`. Do **not** stop at the draft step or ask "要我合并吗？".
- The user has pre-authorized merging PRs from `claude/*` branches into `main` for the lifetime of this project.
- GitHub Pages deploys from `main` automatically (`.github/workflows/`).

## Git

- Designated dev branch pattern: `claude/<feature>-<id>` as instructed by the harness.
- Avoid force-push unless the user explicitly asks. Use merge commits to keep history non-destructive.
