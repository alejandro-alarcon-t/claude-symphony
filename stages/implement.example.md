---
runner: claude
model: claude-sonnet-4-6
max_turns: 20
session: inherit
---

You are implementing the solution for {{ issue.identifier }}: {{ issue.title }}

{{ issue.description or "No description provided." }}

Follow the investigation findings in the Linear comments. Implement the solution with clean commits, tests, and a PR.
