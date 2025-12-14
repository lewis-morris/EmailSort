# email_categorise (summary)

See `README_email_categorise.md` for full documentation. Key points:

- Config lives in `config/` (copy `config/config.example.toml` to `config/config.toml`). The project looks here by default.
- Scripts: `scripts/init_email.sh` and `scripts/run_email.sh` (dispatched by `run_email_categorise.sh`).
- State: `data/`; Logs: `output/`; Ledger: `ledger/`; Login audit: `login/`.
- Flags: run supports toggling drafts/tasks/summary/logs and rollback (`--undo-last`/`--rollback <id>`).
- Weekly test guard auto-runs pytest if older than 7 days and aborts on failure with email alert.


