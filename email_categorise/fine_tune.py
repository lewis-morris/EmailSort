from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from .config import AppConfig, AccountConfig
from .triage_logic import _get_graph
from .utils import utc_now

logger = logging.getLogger("email_categorise.finetune")


def export_reply_dataset(
    config: AppConfig,
    account: AccountConfig,
    output_path: Path,
    max_messages: int = 500,
) -> Dict[str, Any]:
    """Export a simple reply-style dataset from Sent Items.

    This does NOT run any fine-tuning itself; it just prepares a JSONL file
    that you can feed into your own training pipeline (HF, TRL, etc.).

    Each line contains:
      - subject
      - body (HTML or text as returned by Graph)
      - recipients (to + cc addresses)
      - sentDateTime
    """

    graph = _get_graph(config, account)
    sent = graph.list_sent_messages_since(
        config.triage.tone_profile_lookback_days, max_messages=max_messages
    )

    output_path = output_path.expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with output_path.open("w", encoding="utf-8") as f:
        for msg in sent:
            body = (msg.get("body") or {}).get("content") or msg.get("bodyPreview") or ""
            subject = msg.get("subject") or ""
            recips = (msg.get("toRecipients") or []) + (msg.get("ccRecipients") or [])
            recipients = []
            for r in recips:
                ed = r.get("emailAddress") or {}
                addr = (ed.get("address") or "").strip()
                if addr:
                    recipients.append(addr)

            item: Dict[str, Any] = {
                "subject": subject,
                "body": body,
                "recipients": recipients,
                "sentDateTime": msg.get("sentDateTime"),
            }
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            written += 1

    logger.info(
        "Exported %s Sent Items examples for %s to %s",
        written,
        account.email,
        output_path,
    )

    return {
        "account": account.email,
        "examples": written,
        "path": str(output_path),
        "exported_at": utc_now().isoformat(),
    }


def train_local_reply_model(
    dataset_path: Path,
    base_model_id: str,
    output_dir: Path,
    *,
    max_steps: int = 500,
    learning_rate: float = 5e-5,
    batch_size: int = 1,
    max_seq_len: int = 1024,
) -> Dict[str, Any]:
    """Minimal local fine-tune helper for a reply-style model.

    - Uses Hugging Face `transformers` (and `torch`) for causal LM fine-tuning.
    - Treats each exported Sent Item body as a training example in your voice.
    - Does NOT run by default; you must call the CLI subcommand explicitly.

    This function is intentionally simple and intended for small, local runs
    (e.g. LoRA/PEFT can be layered on later if you wish).
    """

    try:
        import torch  # type: ignore[import]
        from datasets import load_dataset  # type: ignore[import]
        from transformers import (  # type: ignore[import]
            AutoModelForCausalLM,
            AutoTokenizer,
            DataCollatorForLanguageModeling,
            Trainer,
            TrainingArguments,
        )
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Fine-tuning requires 'torch', 'transformers', and 'datasets' to be "
            "installed in your environment."
        ) from exc

    dataset_path = dataset_path.expanduser()
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {dataset_path}")

    output_dir = output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading dataset from %s", dataset_path)
    ds = load_dataset("json", data_files=str(dataset_path))["train"]

    def _format_example(example: Dict[str, Any]) -> Dict[str, Any]:
        subject = (example.get("subject") or "").strip()
        body = (example.get("body") or "").strip()
        text = body or subject
        return {
            "text": text,
        }

    ds = ds.map(_format_example, remove_columns=ds.column_names)

    logger.info("Loading base model %s", base_model_id)
    tokenizer = AutoTokenizer.from_pretrained(base_model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def _tokenize(batch: Dict[str, Any]) -> Dict[str, Any]:
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=max_seq_len,
        )

    tokenized = ds.map(_tokenize, batched=True, remove_columns=["text"])

    model = AutoModelForCausalLM.from_pretrained(base_model_id)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    args = TrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=batch_size,
        num_train_epochs=1,
        learning_rate=learning_rate,
        max_steps=max_steps,
        logging_steps=10,
        save_steps=50,
        save_total_limit=2,
        prediction_loss_only=True,
    )

    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=tokenized,
        data_collator=data_collator,
    )

    logger.info(
        "Starting fine-tune: steps=%s, lr=%s, batch_size=%s, max_seq_len=%s",
        max_steps,
        learning_rate,
        batch_size,
        max_seq_len,
    )
    trainer.train()

    logger.info("Saving fine-tuned model to %s", output_dir)
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    return {
        "base_model": base_model_id,
        "dataset": str(dataset_path),
        "output_dir": str(output_dir),
        "max_steps": max_steps,
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "max_seq_len": max_seq_len,
        "finished_at": utc_now().isoformat(),
    }

