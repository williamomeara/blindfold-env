---
name: blindfold
description: Manage .env secrets without exposing values to AI assistants
---

# blindfold — Secret Management

Use the `blindfold` CLI to manage .env files. NEVER read or write .env files directly.

## Commands
- `blindfold set <KEY>` — Set a secret (prompts user via /dev/tty)
- `blindfold set <KEY> --clipboard` — Set from clipboard
- `blindfold get <KEY>` — Show masked value
- `blindfold list` — List all key names
- `blindfold delete <KEY>` — Remove a key
- `blindfold rename <OLD> <NEW>` — Rename a key
- `blindfold copy <KEY> <NEW_KEY>` — Duplicate a value
- `blindfold import <FILE>` — Bulk import from another .env
- `blindfold --env production <command>` — Target .env.production
