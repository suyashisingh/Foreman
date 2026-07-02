# Foreman

Autonomous multi-agent software engineering platform. Give it a GitHub
issue — four specialized AI agents plan, write, test, and review code
in an isolated cloud environment. You approve the diff before anything
merges.

**Live demo:** https://foreman-gcokyb54y-suyashi.vercel.app  
**Source:** https://github.com/suyashisingh/Foreman

---

## What it does

Foreman takes a natural-language task description and a registered
GitHub repository, then runs a four-agent pipeline entirely in the
cloud:

1. **Planner** — searches the codebase via pgvector RAG, produces a
   step-by-step implementation plan
2. **Coder** — implements the plan with file-editing tool calls inside
   an isolated e2b sandbox. Never touches your machine.
3. **Tester** — runs pytest inside the same sandbox. On failure, sends
   the full output back to Coder for targeted fixes — up to 3 retry
   loops.
4. **Reviewer** — reads the final diff, rates risk (low/medium/high),
   writes a PR title and description, and halts the pipeline for your
   approval.

Nothing merges without an explicit approve click.

---

## Architecture
