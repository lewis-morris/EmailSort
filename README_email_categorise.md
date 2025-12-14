# email_categorise (Graph + MSAL + Codex exec)

This project is designed to live at:

`~/.codex-tools/bin/email_categorise`

It runs as a normal CLI so you can schedule it (cron/systemd timers) and it stores all state under:

- `./data/` (MSAL cache, sender stats, tone profiles, run state, weekly test marker)
- `./output/` (timestamped logs + markdown run reports)
- `./ledger/` (run-level action ledgers for rollback)
- `./login/` (non-sensitive login/session metadata per run)

## What works today

### Mail triage (Inbox)
For each configured mailbox it can:

- Fetch Inbox messages from the last N days that do **not** have category `Processed`
- Pull a small thread context via `conversationId`
- Ask an LLM (via `codex exec`) to:
  - choose **one primary category**
  - add optional secondary categories (Complete/Possibly Complete)
  - set a follow-up flag (Today/Tomorrow/This week/Next week/No date/Mark as complete)
  - decide if a reply is needed
  - optionally draft a reply in your tone
  - optionally emit a task summary
- Apply results to the message:
  - add `Processed` category
  - apply your category, importance, follow-up flag, and read/unread rules
  - optionally create a **draft reply** (never auto-sends)
  - optionally append tasks to `data/<account>/tasks.md`
  - optionally send a single “informational digest” email

The followup flag uses the `followupFlag` resource, and Graph requires startDateTime to set a due date.  
https://learn.microsoft.com/en-us/graph/api/resources/followupflag?view=graph-rest-1.0

The sendMail endpoint supports both `/me/sendMail` and `/users/{id}/sendMail` and requires `Mail.Send` permission.  
https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0

The message resource includes `categories`, `flag`, `importance`, and `isRead` fields we update.  
https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0

### Tone profiling (Sent Items)
On `init`, it builds **tone profiles** from Sent Items:

- top 10 contacts you reply to
- a default profile for everyone else

This is stored per account in:

`data/<account>/tone_profiles.json`

and is injected into the prompt for drafting replies.

### LLM backend (Codex + OSS/local)
This project now routes all model calls through a small **model registry** and a
provider-agnostic client:

- Models are defined in `config/config.toml` under `[models.*]` and selected via
  `[llm]` (`triage_model` / `reply_model`).
- For **Codex** / **Codex OSS**, it still shells out to `codex exec` under the hood
  (non-interactive mode, stdin via `-`, JSON Schema validation).
  - `codex exec` reference: https://developers.openai.com/codex/cli/reference/
  - JSON schema / SDK docs: https://developers.openai.com/codex/sdk/
- For **OpenAI / OpenAI-compatible** providers, it uses the `openai` Python client
  with an optional `base_url` so you can point at local servers (vLLM, TGI,
  LM Studio, Ollama `/v1`, etc.).
- For **Hugging Face local** models (`provider="hf-local"`), it loads a local
  `transformers`/`torch` model id and generates JSON directly on your machine
  (no HTTP hop); good candidates include:
  - Triage / tone: `microsoft/Phi-3.5-mini-instruct`, `Qwen/Qwen2.5-3B-Instruct`,
    `mistralai/Mistral-7B-Instruct-v0.3`.
  - Replies: `meta-llama/Meta-Llama-3.1-8B-Instruct`, `Qwen/Qwen2.5-7B-Instruct`,
    `mistralai/Mixtral-8x7B-Instruct-v0.1` (heavier).

All providers go through the same JSON Schema validation step using the schemas
in `email_categorise/json_schemas`, and the validated outputs are written under
`data/<account>/...` for auditability.

## Things you enabled that are NOT used yet (future options)

You enabled a large set of Graph permissions. That’s fine, but this tool currently only uses:

- Mailbox read/write + send
- Optional draft replies (createReply)
- Optional local “tasks.md” (not Graph Tasks yet)

Future expansions you can add (not implemented yet, but the permissions you granted cover them):

- Create Microsoft To Do tasks (Graph Tasks) if you want real task objects
- Create/update calendar events (Calendars.ReadWrite)
- Create/update contacts (Contacts.ReadWrite)
- Use mailbox configuration objects for app state (MailboxConfigItem.*)
- CustomTags (if you later decide to use them for additional triage metadata)

## Auth modes

This tool supports two modes:

### 1) application (recommended for cron)
- No browser login
- Uses client credentials + `.default` scopes
- Requires **Application** permissions and admin consent
- Uses Graph endpoints under `/users/{mailbox}/...`

### 2) delegated
- Browser login on first use (MSAL)
- Uses cached tokens afterwards
- Uses Graph endpoints under `/me/...` for the signed-in user

Important: MSAL will throw an error if you include reserved scopes like `openid/profile/offline_access` in requested scopes.
So, in delegated mode, only include resource scopes like `Mail.ReadWrite`.  
MSAL has an `exclude_scopes` option and discusses offline_access behaviour in its Python API docs:
https://learn.microsoft.com/en-us/python/api/msal/msal.application.clientapplication?view=msal-py-latest

## Install (python-tools venv)

```bash
~/.codex-tools/environments/python-tools/bin/pip install -r ~/.codex-tools/bin/email_categorise/requirements.txt
```

## Setup (config)

```bash
cd ~/.codex-tools/bin/email_categorise
cp config/config.example.toml config/config.toml
```

Key settings:
- `[azure]` default app credentials; per-account overrides are supported under `[[accounts]].azure_overrides`.
- `[triage]` defaults for behaviours; per-account overrides under `[[accounts]].triage_overrides`.
- `[triage.priority_read_state]` controls post-triage read/unread per category.
- Env var for secrets: `MS_GRAPH_CLIENT_SECRET` (or override name per account).

Per-account overrides (example)
--------------------------------
You can override most Azure and triage settings for a specific mailbox without changing the global defaults:

```toml
[[accounts]]
email = "mike@colemanbros.co.uk"
label = "mike"

# Azure overrides for this mailbox (auth/tenant/secret)
[ [accounts].azure_overrides ]
client_id = "slakdl;askjkd;23472fe8-0700-48e1-a0e3-d351cc6bda0c"
tenant_id = "92f217f9-7fcf-as';kd;l'askdasl;k4d40-a990-f36c1737cfa8"
client_secret_env = "MS_GRAPH_CLIENT_SECRETER"  # env var name holding the secret

# Triage behaviour overrides for this mailbox
[ [accounts].triage_overrides ]
log_to_file = true
send_summary_email = true
summary_email_to = "mike@colemanbros.co.uk"  # optional, defaults to global
```

Notes:
- Any key omitted in an overrides block falls back to the global `[azure]` / `[triage]` defaults.
- `tenant_id` can also be set directly on the account (`tenant_id = "..."`), but values in `azure_overrides.tenant_id` win if both are present.
- `client_secret_env` is the name of an environment variable (per-account if overridden) that must be set in the shell before running.

## Run

### Init (build sender stats + tone profiles)
```bash
./run_email_categorise.sh init --config config/config.toml [-a user@domain] [--run-id RID]
```

### Daily triage run
```bash
./run_email_categorise.sh run --config config/config.toml [-a user@domain] [--run-id RID] \\
  [--draft-replies|--no-draft-replies] [--create-tasks|--no-create-tasks] \\
  [--summary-email|--no-summary-email] [--log-to-file|--no-log-to-file] \\
  [--undo-last | --rollback RUN_ID]
```

Outputs:
- `output/email_categorise_<cmd>_<UTCSTAMP>.log`
- `output/email_categorise_<cmd>_<UTCSTAMP>.last.md`
- Ledger per run: `ledger/<account>_<run-id>.json`; index at `ledger/index.json`
- Login audit: `login/<account>_<timestamp>_<run-id>.json`

State:
- `data/<account>/state.json`
- `data/<account>/sender_stats.json`
- `data/<account>/tone_profiles.json`
- `data/msal_token_cache.bin`
- `data/last_tests.json` (weekly test guard marker)

### New helper scripts
- `scripts/init_email.sh` — wraps init with defaults and logging.
- `scripts/run_email.sh` — wraps daily run, defaulting all actions to on; flags above toggle.
`run_email_categorise.sh` dispatches to these when `init`/`run` is used.

### Weekly test guard
- On `init`/`run`, if `data/last_tests.json` older than 7 days, runs `pytest`.
- Aborts triage on failure and emails a failure notice to `triage.summary_email_to` (or account email).

### Rollback
- Each run records message patches, draft creations, and task file appends in `ledger/`.
- Use `--undo-last` or `--rollback <run-id>` to restore categories/read/flags, delete drafts, and truncate task appends.
