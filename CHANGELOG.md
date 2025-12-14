# Changelog

All notable changes to this project will be documented in this file.

The version number is defined in `email_categorise/__init__.py` and mirrored in
`pyproject.toml`.

## [0.3.0] - 2025-12-14

### Added
- Model registry in config (`[llm]` + `[models.*]`) so triage and reply models
  can be swapped without code changes.
- Provider-agnostic LLM client (`ModelClient` + `StructuredLLMRunner`) with
  support for:
  - Codex / Codex OSS via `codex exec`.
  - OpenAI / OpenAI-compatible HTTP endpoints (local vLLM / TGI / LM Studio / Ollama).
  - Local Hugging Face models (`hf-local`) using `transformers` / `torch`.
- JSON Schema-based validation of all LLM outputs using the schemas in
  `email_categorise/json_schemas`, with validated responses written under
  `data/<account>/...` for auditability.
- Fine-tune tooling:
  - `export-finetune` CLI subcommand to export Sent Items into JSONL for training
    a reply model in the user's tone.
  - `train-finetune` CLI subcommand to run a small local fine-tune using
    `torch`, `transformers`, and `datasets`.
- Extended configuration example in `config/config.example.toml` documenting:
  - Multiple model providers and example model choices.
  - How to register a fine-tuned local reply model (`models.reply_finetuned`).

### Changed
- Primary README reorganised to describe:
  - New helper scripts (`scripts/init_email.sh`, `scripts/run_email.sh`).
  - Wrapper script `run_email_categorise.sh` and direct `python -m` usage.
  - Weekly test guard behaviour and rollback support.
- Project metadata switched to `pyproject.toml`-based installation; `requirements.txt`
  is no longer used for main installs.
- `pyproject.toml` updated to:
  - Set version to `0.3.0` (matching `__init__`).
  - Add `jsonschema` as a core dependency (used for validating model output).
  - Declare optional extras:
    - `openai` (installs the `openai` client).
    - `hf-local` (installs `torch` and `transformers`).
    - `finetune` (installs `torch`, `transformers`, and `datasets`).

### Removed
- `python-dotenv` from the core dependencies in favour of the built-in `.env`
  loader in `email_categorise.utils.load_env_file`.

## [0.2.0] - 2025-12-14

> Version inferred from the initial repository state where the codebase already
> reported `__version__ = "0.3.0"` but packaging and docs had not yet been
> aligned. This entry groups the earlier structural and behavioural work.

### Added
- Dedicated `config/` directory with `config.example.toml` and support for:
  - Global `[auth]`, `[azure]`, `[triage]`, `[llm]` settings.
  - Per-account overrides via `[[accounts]].azure_overrides` and
    `[[accounts]].triage_overrides`.
- Core mail triage pipeline:
  - Fetch recent Inbox messages that do not have the `Processed` category.
  - Build lightweight thread context and sender stats.
  - Call an LLM to assign primary/secondary categories, flags, tasks, and draft
    replies, validated via JSON Schema.
  - Apply categories, flags, importance, and read/unread state back to Graph.
  - Optionally create draft replies and append tasks to `data/<account>/tasks.md`.
- Tone profiling (`init` flow):
  - Scan Sent Items to build `sender_stats.json` and `tone_profiles.json`.
  - Inject tone profiles into reply drafting prompts.
- Outlook master category colour management, ensuring the standard palette for:
  - `Urgent`, `Priority 1/2/3`, `Marketing`, `Informational`, `No reply needed`,
    `Complete`, `Possibly Complete`, `Processed`, `Payment Request`, `Invoice`,
    `Order Confirmation`, `Issue`, `Task`.
- Weekly test guard:
  - Store last test run timestamp in `data/last_tests.json`.
  - On `init`/`run`, auto-run `pytest` if older than 7 days and abort on failure
    with an email notification.
- Run ledger and rollback:
  - Per-run ledger files in `ledger/` recording message patches, draft creations,
    and task file appends.
  - CLI flags `--undo-last` and `--rollback <run-id>` to revert a run.
- Login audit trail in `login/` capturing non-sensitive per-run metadata
  (account, auth mode, tenant, run id, timestamp).
- Shell helper scripts:
  - `scripts/init_email.sh` for first-time account setup (tone/stat learning).
  - `scripts/run_email.sh` for daily triage runs with feature toggles.
  - `scripts/run_email_categorise.sh` wrapper dispatching to the helpers or to
    `python -m email_categorise`.

### Changed
- Centralised configuration handling in `email_categorise.config` using
  dataclasses (`AppConfig`, `AccountConfig`, `TriageConfig`, etc.).
- Triaging logic refactored into `email_categorise.triage_logic` using
  provider-agnostic LLM runners and structured prompts described in
  `email_categorise/email_triage_agent.md`.

## [0.1.0] - 2025-12-14

### Added
- Initial project bootstrapping:
  - Basic `email_categorise` package with version constant in `__init__.py`.
  - Minimal `pyproject.toml` with core dependencies (`msal`, `msal-extensions`,
    `requests`, `toml`, `pytest`).
  - Skeleton CLI entry point and repository layout under
    `~/.codex-tools/bin/email_categorise`.

