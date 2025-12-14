from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .config import AppConfig, ModelDefinition

logger = logging.getLogger("email_categorise.model")


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class ModelClient:
    """Small wrapper around either:

    - `codex exec` (recommended for this project) so you can use your ChatGPT plan auth
      and Codex model selection.
    - The OpenAI API (optional fallback) if you want to run without Codex.

    The rest of the code calls `chat_json(...)` and expects a dict.
    """

    definition: ModelDefinition

    def chat_json(
        self,
        system_prompt: str,
        user_content: str,
        *,
        schema_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        provider = (self.definition.provider or "").strip().lower()

        if provider in {"codex", "codex-oss"}:
            if not schema_path:
                raise ValueError(
                    f"schema_path is required for provider '{provider}' (model={self.definition.name})."
                )
            return self._chat_json_codex(
                system_prompt, user_content, schema_path=schema_path
            )

        if provider in {"openai", "openai-compatible"}:
            return self._chat_json_openai(system_prompt, user_content)

        if provider == "hf-local":
            return self._chat_json_hf_local(system_prompt, user_content)

        raise ValueError(
            f"Unknown model provider '{self.definition.provider}' for model '{self.definition.name}'. "
            "Supported: codex, codex-oss, openai, openai-compatible, hf-local"
        )

    # -----------------------------
    # Codex CLI provider
    # -----------------------------

    def _chat_json_codex(
        self, system_prompt: str, user_content: str, *, schema_path: Path
    ) -> Dict[str, Any]:
        schema_path = schema_path.expanduser().resolve()
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        codex_bin = (self.definition.codex_bin or "codex").strip() or "codex"
        provider = (self.definition.provider or "").strip().lower()

        # We pipe the prompt via stdin (PROMPT = "-") so we don't need to worry about shell quoting.
        prompt = (
            "System instructions:\n"
            + system_prompt.strip()
            + "\n\nUser input:\n"
            + user_content.strip()
            + "\n\nReturn ONLY valid JSON that matches the provided JSON Schema."
        )

        with tempfile.TemporaryDirectory(prefix="email_categorise_codex_") as td:
            out_path = Path(td) / "last_message.txt"

            cmd = [
                codex_bin,
                "exec",
                "-",
                "--model",
                self.definition.model,
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(out_path),
            ]

            if provider == "codex-oss":
                cmd.append("--oss")

            if self.definition.codex_profile:
                cmd.extend(["--profile", self.definition.codex_profile])

            for ov in self.definition.codex_config:
                # Supports `-c key=value` multiple times.
                cmd.extend(["-c", ov])

            logger.debug("Running Codex CLI: %s", " ".join(cmd))
            proc = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                capture_output=True,
            )

            if proc.returncode != 0:
                stderr = (proc.stderr or "").strip()
                stdout = (proc.stdout or "").strip()
                logger.error(
                    "codex exec failed (rc=%s). stderr=%s", proc.returncode, stderr
                )
                raise RuntimeError(
                    "codex exec failed. "
                    f"rc={proc.returncode}. "
                    f"stderr={stderr[:1000]} "
                    f"stdout={stdout[:1000]}"
                )

            raw = ""
            if out_path.exists():
                raw = out_path.read_text(encoding="utf-8")
            else:
                # Fallback. Not expected when --output-last-message works.
                raw = proc.stdout or ""

        return _parse_json_lenient(raw)

    # -----------------------------
    # OpenAI API provider (optional)
    # -----------------------------

    def _chat_json_openai(
        self, system_prompt: str, user_content: str
    ) -> Dict[str, Any]:
        # Lazy import so Codex-only installs don't need the dependency.
        from .utils import load_env_file

        load_env_file()
        try:
            from openai import OpenAI  # type: ignore[import]
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "The 'openai' Python package is required for provider='openai' or 'openai-compatible'. "
                "Install it, or switch provider to 'codex' to use the Codex CLI instead."
            ) from exc

        api_key = os.environ.get(self.definition.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Environment variable {self.definition.api_key_env} is not set. "
                f"Cannot authenticate for model {self.definition.name}."
            )

        kwargs: Dict[str, Any] = {"api_key": api_key}
        if self.definition.base_url:
            kwargs["base_url"] = self.definition.base_url

        client = OpenAI(**kwargs)
        logger.debug(
            "Calling OpenAI model %s (provider=%s, base_url=%s)",
            self.definition.model,
            self.definition.provider,
            self.definition.base_url or "https://api.openai.com/v1",
        )

        completion = client.chat.completions.create(
            model=self.definition.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = completion.choices[0].message.content
        if not content:
            raise RuntimeError("Model returned empty content")
        return _parse_json_lenient(content)

    # -----------------------------
    # Hugging Face local provider
    # -----------------------------

    def _chat_json_hf_local(
        self, system_prompt: str, user_content: str
    ) -> Dict[str, Any]:
        """Run a local Hugging Face model to produce JSON.

        This assumes you have installed `transformers` (and usually `torch`)
        and downloaded the model specified in `self.definition.model`.
        """

        try:
            import torch  # type: ignore[import]
            from transformers import (  # type: ignore[import]
                AutoModelForCausalLM,
                AutoTokenizer,
            )
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Provider 'hf-local' requires the 'transformers' and 'torch' "
                "packages to be installed."
            ) from exc

        # Lazy-load and cache model/tokenizer on the client instance.
        if not hasattr(self, "_hf_model"):
            model_id = self.definition.model
            if not model_id:
                raise RuntimeError(
                    f"Model id is required for provider='hf-local' "
                    f"(definition={self.definition.name})."
                )

            logger.info("Loading Hugging Face model %s for %s", model_id, self.definition.name)
            tokenizer = AutoTokenizer.from_pretrained(model_id)
            model = AutoModelForCausalLM.from_pretrained(model_id)

            device = self.definition.hf_device or (
                "cuda" if torch.cuda.is_available() else "cpu"
            )
            model.to(device)

            setattr(self, "_hf_tokenizer", tokenizer)
            setattr(self, "_hf_model", model)
            setattr(self, "_hf_device", device)

        tokenizer = getattr(self, "_hf_tokenizer")
        model = getattr(self, "_hf_model")
        device = getattr(self, "_hf_device")

        prompt = (
            "System instructions:\n"
            + system_prompt.strip()
            + "\n\nUser input:\n"
            + user_content.strip()
            + "\n\nReturn ONLY valid JSON that matches the expected schema."
        )

        inputs = tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}

        max_new_tokens = self.definition.hf_max_new_tokens or 512

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.2,
            )

        # Only keep tokens generated beyond the prompt.
        generated = output_ids[0][inputs["input_ids"].shape[1] :]
        text = tokenizer.decode(generated, skip_special_tokens=True)
        return _parse_json_lenient(text)


def _parse_json_lenient(text: str) -> Dict[str, Any]:
    """Parse model output that *should* be JSON.

    Codex CLI is schema-validated, but we still keep this robust:
    - Strips code fences.
    - Tries full JSON parse.
    - Falls back to extracting the first {...} block.
    """

    raw = (text or "").strip()
    if not raw:
        raise RuntimeError("Model returned empty output")

    # Strip common formatting wrappers.
    if raw.startswith("```"):
        raw = raw.strip("`")
        # If it was ```json ...```, strip the leading 'json' token.
        raw = raw.lstrip().removeprefix("json").lstrip()

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("Model JSON was not an object")
        return parsed
    except json.JSONDecodeError:
        match = _JSON_RE.search(raw)
        if not match:
            logger.error("Could not find JSON object in model output: %s", raw[:1000])
            raise RuntimeError("Model returned invalid JSON")
        try:
            parsed = json.loads(match.group(0))
            if not isinstance(parsed, dict):
                raise RuntimeError("Model JSON was not an object")
            return parsed
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse extracted JSON. Raw=%s", raw[:1000])
            raise RuntimeError("Model returned invalid JSON") from exc


@dataclass
class StructuredLLMRunner:
    """Adapter to run a ModelClient with JSON Schema validation and file output.

    This mirrors the existing CodexRunner.run_with_schema interface so that
    triage and init code can stay provider-agnostic.
    """

    client: ModelClient

    def run_with_schema(
        self, prompt: str, schema_path: Path, output_path: Path
    ) -> Dict[str, Any]:
        schema_path = schema_path.expanduser().resolve()
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        output_path = output_path.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Call through the generic interface. We treat the entire prompt as the
        # "user" content; system_prompt is left empty.
        result = self.client.chat_json(
            system_prompt="",
            user_content=prompt,
            schema_path=schema_path,
        )

        # Provider-agnostic JSON Schema validation.
        try:
            import jsonschema  # type: ignore[import]
        except Exception as exc:  # pragma: no cover
            logger.error(
                "jsonschema package is required for schema validation. Error: %s", exc
            )
            raise RuntimeError(
                "jsonschema package is required for validating LLM output "
                "against JSON schemas."
            ) from exc

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        try:
            jsonschema.validate(instance=result, schema=schema)  # type: ignore[attr-defined]
        except jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
            logger.error("Model output failed schema validation: %s", exc)
            raise

        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result


def build_model_clients(config: AppConfig) -> Dict[str, ModelClient]:
    return {
        name: ModelClient(definition=definition)
        for name, definition in config.models.items()
    }
