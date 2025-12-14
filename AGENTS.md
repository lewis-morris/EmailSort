# Repository Guidelines

## Project Structure & Module Organization
- Source lives in `email_categorise/` (CLI wiring in `cli.py`, config loading in `config.py`, Graph + MSAL helpers in `auth.py`/`graph_client.py`, LLM runners in `model_client.py` (Codex/OpenAI/HF), triage logic in `triage_logic.py`, shared helpers in `utils.py`).
- Entry points:
  - Helper scripts: `scripts/init_email.sh` and `scripts/run_email.sh` (preferred for day-to-day use).
  - Wrapper: `run_email_categorise.sh` (or `scripts/run_email_categorise.sh` in this repo) which dispatches to the helper scripts or `python -m email_categorise ...`.
  - Direct invocation for debugging: `python -m email_categorise ...`.
- Config: `config/config.toml` (copy from `config/config.example.toml`). Runtime state under `data/`; logs and markdown reports under `output/`; run-level ledgers under `ledger/`; login/session metadata under `login/`.
- Schemas/prompts: `email_categorise/json_schemas` and `email_categorise/email_triage_agent.md` guide model outputs.

## Setup, Build & Run
- Install dependencies with the pinned toolchain using the project metadata (Python 3.12+):
  - From this repo: `cd ~/.codex-tools/bin/email_categorise`
  - Then: `~/.codex-tools/environments/python-tools/bin/pip install .`
  - Optionally, if you use `uv`: `uv sync` will honour `pyproject.toml` and `uv.lock`.
- Initialise accounts (build sender stats + tone profiles): `./scripts/init_email.sh --config config/config.toml [-a user@domain]` (or `./run_email_categorise.sh init ...` if you have the wrapper on PATH).
- Daily triage run: `./scripts/run_email.sh --config config/config.toml [-a user@domain]` (or `./run_email_categorise.sh run ...`).
- Direct invocation (useful for debugging or extra subcommands like fine-tuning): `python -m email_categorise run --config config/config.toml -v`.
- Logs are tee’d to `output/email_categorise_<cmd>_<UTCSTAMP>.log`; the latest markdown summary is `<cmd>_..._.last.md`. Per-run ledgers live in `ledger/`, and login audit records live in `login/`.

## Coding Style & Naming Conventions
- Follow PEP 8; 4-space indents; type hints preferred (modules already use `from __future__ import annotations`).
- Keep modules/function names snake_case; classes in PascalCase; config keys match TOML structure.
- Use the built-in `logging` logger namespacing (see `email_categorise.cli`); avoid print except for user-facing summaries.
- Prefer dataclasses for config-like objects (existing pattern in `config.py`).

## Testing Guidelines
- `pytest` is available; new logic should come with tests where practical. Suggested layout: `tests/test_*.py` mirroring module names.
- Existing integration coverage lives in `tests/test_integration.py` and exercises live Graph access (categories, flags, draft replies). These tests:
  - Expect `config/config.toml` to be configured for at least one mailbox.
  - Require a valid `MS_GRAPH_CLIENT_SECRET` (or per-account override) in the environment.
  - Are marked as integration tests and should not run in CI against real tenant data.
- A weekly test guard is wired into the CLI: on `init`/`run`, if `data/last_tests.json` is older than 7 days, the tool runs `pytest` and aborts triage on failure, sending a failure notification email.
- For manual smoke checks, run `./scripts/init_email.sh ...` then `./scripts/run_email.sh ...` against a test mailbox; confirm categories, flags, drafts, and summary emails.
- Keep fixtures/seeds small; never commit real tokens or mail content—use redacted samples.

## Commit & Pull Request Guidelines
- Repository has no commit history; use concise, imperative subjects (e.g., `Add delegated auth fallback`) and keep body lines ≤72 chars.
- Reference issues or TODOs when relevant; note config or schema changes in the body.
- PRs should include: purpose, config/secret expectations, testing performed (commands + mailbox used), and screenshots or log excerpts if behaviour changed.

## Security & Configuration Tips
- Never commit secrets; supply `MS_GRAPH_CLIENT_SECRET` via environment only. `config.toml` should hold IDs, not secrets.
- `data/` contains token caches and sender stats—keep it out of PR diffs unless intentionally modifying test fixtures.
- When adding new Graph scopes or LLM models, document them in `config.example.toml` and mention the required environment variables in the PR description.
