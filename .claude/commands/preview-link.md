Give the user the Vercel preview link of the current branch (or the branch they name) right away:

1. `bash scripts/preview_url.sh [branch]` and hand over the start page (Belgrade) and, if it matters, the Zürich reference.
2. Don't wait for Vercel's PR comment; it isn't reliable.
3. If the user needs to know whether the preview already serves the latest commit, check as the `steward` skill says (a changed string in a served file), then say so.
