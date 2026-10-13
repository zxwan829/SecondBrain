# SecondBrain project guidance

This repository is the canonical source for SecondBrain application code, development tooling, and approved project baseline documents. Read `docs/baseline/00-CURRENT.md` for current project status and consult `Agent-Rules.md` and the relevant baseline or business specification for task-specific rules. Do not use NAS or Synology Drive copies as code or documentation authorities.

Develop on a local Git clone; iMac and MBA are independent development machines that share reviewed changes through the private GitHub repository using normal Git commit, push, and pull. Prefer local tests and do not require GitHub Actions or PR review. NAS hosts Docker services and business data; Obsidian stores notes, knowledge, and readable project references, not development source. Any formal NAS deployment requires explicit user authorization.
