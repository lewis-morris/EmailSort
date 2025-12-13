# Repository Guidelines

## Project Structure & Module Organization
- Source lives in `email_categorise/` (CLI wiring in `cli.py`, config loading in `config.py`, Graph + MSAL helpers in `auth.py`/`graph_client.py`, LLM runners in `codex_runner.py`, triage logic in `triage_logic.py`, shared helpers in `utils.py`).
- Entry points: `run_email_categorise.sh` (preferred) or `python -m email_categorise ...`. A thin `main.py` also exists for tooling.
- Config: `config.toml` (copy from `config.example.toml`). Runtime state under `data/`; logs and markdown reports under `output/`.
- Schemas/prompts: `email_categorise/json_schemas` and `email_categorise/email_triage_agent.md` guide model outputs.

## Setup, Build & Run
- Install dependencies with the pinned toolchain: `~/.codex-tools/python-tools/bin/pip install -r requirements.txt` (Python 3.12+).
- Initialise accounts (build sender stats + tone profiles): `./run_email_categorise.sh init --config config.toml [-a user@domain]`.
- Daily triage run: `./run_email_categorise.sh run --config config.toml [-a user@domain]`.
- Direct invocation (useful for debugging): `python -m email_categorise run --config config.toml -v`.
- Logs are tee’d to `output/email_categorise_<cmd>_<UTCSTAMP>.log`; the latest markdown summary is `<cmd>_..._.last.md`.

## Coding Style & Naming Conventions
- Follow PEP 8; 4-space indents; type hints preferred (modules already use `from __future__ import annotations`).
- Keep modules/function names snake_case; classes in PascalCase; config keys match TOML structure.
- Use the built-in `logging` logger namespacing (see `email_categorise.cli`); avoid print except for user-facing summaries.
- Prefer dataclasses for config-like objects (existing pattern in `config.py`).

## Testing Guidelines
- No automated test suite is present yet; add `pytest` when introducing new logic. Suggested layout: `tests/test_*.py` mirroring module names.
- For manual smoke checks, run `./run_email_categorise.sh init ...` then `./run_email_categorise.sh run ...` against a test mailbox; confirm categories, flags, and generated drafts.
- Keep fixtures/seeds small; never commit real tokens or mail content—use redacted samples.

## Commit & Pull Request Guidelines
- Repository has no commit history; use concise, imperative subjects (e.g., `Add delegated auth fallback`) and keep body lines ≤72 chars.
- Reference issues or TODOs when relevant; note config or schema changes in the body.
- PRs should include: purpose, config/secret expectations, testing performed (commands + mailbox used), and screenshots or log excerpts if behaviour changed.

## Security & Configuration Tips
- Never commit secrets; supply `MS_GRAPH_CLIENT_SECRET` via environment only. `config.toml` should hold IDs, not secrets.
- `data/` contains token caches and sender stats—keep it out of PR diffs unless intentionally modifying test fixtures.
- When adding new Graph scopes or LLM models, document them in `config.example.toml` and mention the required environment variables in the PR description.
