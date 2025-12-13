# email_categorise (Graph + MSAL + Codex exec)

This project is designed to live at:

`~/.codex-tools/email_categorise`

It runs as a normal CLI so you can schedule it (cron/systemd timers) and it stores all state under:

- `./data/` (MSAL cache, sender stats, tone profiles, run state)
- `./output/` (timestamped logs + markdown run reports)

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

### LLM backend (Codex exec)
This project calls models via **Codex CLI non-interactive mode**:

- `codex exec` supports piping prompt content from stdin using `-`.  
  https://developers.openai.com/codex/cli/reference/
- It supports **structured JSON** via `--output-schema <path>` and saving output with `-o`.  
  https://developers.openai.com/codex/sdk/
- It supports local OSS providers (Ollama) via `--oss`.  
  https://developers.openai.com/codex/cli/reference/

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
~/.codex-tools/python-tools/bin/pip install -r ~/.codex-tools/email_categorise/requirements.txt
```

## Setup (config)

```bash
cd ~/.codex-tools/email_categorise
cp config.example.toml config.toml
```

Edit:
- `[azure].client_id`
- `[azure].tenant_id` (tenant GUID recommended for application auth)
- Set env var for your client secret:
  - `export MS_GRAPH_CLIENT_SECRET="..."` (do not store in files)
- Add `[[accounts]]` entries

## Run

### Init (build sender stats + tone profiles)
```bash
./run_email_categorise.sh init --config config.toml
```

### Daily triage run
```bash
./run_email_categorise.sh run --config config.toml
```

Outputs:
- `output/email_categorise_<cmd>_<UTCSTAMP>.log`
- `output/email_categorise_<cmd>_<UTCSTAMP>.last.md`

State:
- `data/<account>/state.json`
- `data/<account>/sender_stats.json`
- `data/<account>/tone_profiles.json`
- `data/msal_token_cache.bin`
