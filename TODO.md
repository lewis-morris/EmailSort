- [x] Introduce a dedicated `config/` directory to hold configuration files (current `config.toml`, `config.example.toml`, and per-account overrides); update code/scripts to load from the new path with backward compatibility.

- [x] Support per-account auth settings (client ID, tenant ID, client secret) and behaviour toggles (draft replies, create tasks, send summary, log to file) in config; provide sensible defaults plus per-account overrides.

- [x] Add per-priority handling rules in config to specify whether emails should end in `read` or `unread` state after processing; allow global defaults with per-account overrides.

- [x] Create `scripts/` directory with two entrypoint shell scripts:
  - `scripts/init_email.sh` for first-time account setup: run connectivity checks, poll a small sample of recent emails, and trigger context-learning from past replies; include `--account` and `--help`.
  - `scripts/run_email.sh` for normal daily runs: accept flags (documented in `--help`) to toggle draft replies, task creation, summary email, logging; default to performing all actions when flags omitted.

- [x] Add `--help` flag content and argument parsing for the new run script, allowing overrides (disable drafts/tasks/summary/logging) and account selection.

- [x] Create a `login/` (or similarly named) directory managed by Python helpers to persist authentication/session artifacts in a consistent, timestamped format (agent type, datestamp, run ID, target account) to simplify rollback/audit.

- [x] Design and implement an action log/ledger that records all mutations (drafts, flags, task creations, status changes) with a unique run ID to enable rollback/undo of the last run or recovery after failures.

- [x] Add CLI/flag support for rollback: e.g., `--undo-last` or `--rollback <run-id>` that reverts actions recorded in the ledger.

- [x] Wire the new scripts into existing entrypoints (`run_email_categorise.sh`, `python -m email_categorise ...`) or replace them cleanly; ensure paths/log locations still align with `output/` expectations.

- [x] Add weekly test guard: store last test run timestamp in `data/`; on agent start, if >7 days, auto-run unit tests, halt processing on failure, and send an email notification explaining tests failed and execution stopped.

- [x] Update `README.md` (and `README_email_categorise.md` if needed) to document the new structure (config, scripts, login directories), setup workflow, config keys (auth per account, priority read/unread rules, default actions), usage examples with the new scripts, rollback procedure, and weekly test guard.

- [x] Introduce a proper model registry and `ModelDefinition` type in `config.py`, wiring a `[models]` section in `config.toml` so `llm.triage_model` / `llm.reply_model` map to named model definitions instead of raw Codex model strings.

- [x] Unify LLM access behind a single client abstraction (e.g. `ModelClient.chat_json(...)`) and stop calling `CodexRunner` directly from `triage_logic` and `cli`; provide a Codex-backed implementation that preserves current behaviour.

- [x] Add a new Hugging Face local provider (e.g. `provider = "hf-local"`) in `ModelClient`, including config knobs for model id, device, dtype, max tokens, etc., so local HF models can be used for triage, tone profiling, and reply drafting.

- [x] Optionally support OpenAI-compatible HTTP endpoints in config (e.g. local vLLM / TGI / LM Studio / Ollama servers) by treating them as `provider = "openai-compatible"` with a configurable `base_url`.

- [x] Make JSON Schema validation provider-agnostic: call the selected model through the shared LLM interface, validate responses against the existing schemas in `email_categorise/json_schemas`, and write the validated outputs to disk for auditability (mirroring current Codex behaviour).

- [x] Update `triage_logic` and `cli` so triage and drafting are provider-agnostic, selecting Codex vs Hugging Face vs OpenAI-compatible purely from config without further Python changes.

- [x] Document recommended open-source models for triage/tone profiling vs reply drafting in `config/config.example.toml` and/or `README_email_categorise.md` (for example: Phi-3.5-mini, Qwen2.5-3B/Qwen2.5-7B, Mistral-7B, Llama-3.1-8B).

- [x] Add tooling to export a fine-tune dataset from Sent Items without affecting the main triage flow.

- [ ] Train and register a fine-tuned local reply model in the user's tone, then wire it into config as an optional `[models.reply_finetuned]` entry.
