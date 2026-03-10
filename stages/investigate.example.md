---
runner: claude
model: claude-opus-4-6
max_turns: 5
session: inherit
---

You are investigating issue {{ issue.identifier }}: {{ issue.title }}

{{ issue.description or "No description provided." }}

Your goal is to understand the problem and write a brief investigation summary.

Do NOT write code yet. Focus on:
1. Reading relevant source files
2. Understanding the root cause or requirements
3. Posting your findings as a Linear comment
