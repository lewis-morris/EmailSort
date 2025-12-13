from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("email_categorise.codex")


class CodexRunner:
    def __init__(self, repo_root: Path, provider: str, model: str) -> None:
        self.repo_root = repo_root
        self.provider = provider  # codex | codex-oss
        self.model = model

    def run_with_schema(self, prompt: str, schema_path: Path, output_path: Path) -> Dict[str, Any]:
        schema_path = schema_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "codex",
            "exec",
            "-",  # read prompt from stdin
            "--model",
            self.model,
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--cd",
            str(self.repo_root),
        ]
        if self.provider == "codex-oss":
            cmd.append("--oss")

        logger.debug("Running: %s", " ".join(cmd))

        proc = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
        )

        # Codex streams progress to stderr; capture it for logs.
        if proc.stderr:
            logger.debug("codex stderr: %s", proc.stderr[-2000:])

        if proc.returncode != 0:
            raise RuntimeError(f"codex exec failed (code {proc.returncode}): {proc.stderr.strip()}")

        # Output written to file (-o). Parse it.
        content = output_path.read_text(encoding="utf-8").strip()
        return json.loads(content)
