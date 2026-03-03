
## Secret Management — MANDATORY RULES (blindfold-env)
- NEVER read .env files directly (cat, head, Read tool, grep on .env, etc.)
- NEVER write to .env files directly (echo >>, Edit tool, Write tool, etc.)
- ALL .env interactions MUST go through the `blindfold` CLI tool
- When a user wants to set a secret: `blindfold set <KEY_NAME>`
- To check what keys exist: `blindfold list`
- To see a masked value: `blindfold get <KEY_NAME>`
