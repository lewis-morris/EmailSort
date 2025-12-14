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

- [ ] Consider adding minimal smoke tests (pytest) or validation commands covering new flag parsing, config loading from `config/`, rollback ledger integrity, and weekly test guard behaviour.
