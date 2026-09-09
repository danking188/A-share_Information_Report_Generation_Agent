"""Atomic persistence for report workflow stages and cached artifacts."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


STAGES = (
    "fetch_data",
    "process_data",
    "retrieve_context",
    "generate_sections",
    "export_docx",
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_default(value: Any):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def atomic_write_json(path: str | Path, payload: Dict) -> None:
    """Write JSON with os.replace so interruption cannot leave a partial file."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary_path = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=_json_default)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def load_json(path: str | Path, default: Optional[Dict] = None) -> Dict:
    source = Path(path)
    if not source.exists():
        return {} if default is None else default
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


class WorkflowStateStore:
    """Persist one state file and reusable artifacts for each stock."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.state_dir = self.base_dir / "workflow_states"
        self.cache_dir = self.base_dir / "workflow_cache"

    def state_path(self, stock_code: str) -> Path:
        return self.state_dir / f"{stock_code}.json"

    def artifact_path(self, stock_code: str, name: str) -> Path:
        return self.cache_dir / stock_code / f"{name}.json"

    def start(self, stock_code: str) -> Dict:
        previous = self.load(stock_code)
        if previous.get("status") in {"running", "failed"}:
            previous["status"] = "running"
            previous["updated_at"] = _now()
            previous["last_error"] = None
            self.save(stock_code, previous)
            return previous

        state = {
            "run_id": str(uuid.uuid4()),
            "stock_code": stock_code,
            "status": "running",
            "created_at": _now(),
            "updated_at": _now(),
            "last_error": None,
            "stages": {stage: "pending" for stage in STAGES},
            "artifacts": {},
        }
        self.save(stock_code, state)
        return state

    def load(self, stock_code: str) -> Dict:
        return load_json(self.state_path(stock_code), {})

    def save(self, stock_code: str, state: Dict) -> None:
        state["updated_at"] = _now()
        atomic_write_json(self.state_path(stock_code), state)

    def mark_stage(
        self,
        stock_code: str,
        stage: str,
        status: str,
        artifact: Optional[str] = None,
    ) -> Dict:
        if stage not in STAGES:
            raise ValueError(f"未知工作流阶段: {stage}")
        state = self.load(stock_code) or self.start(stock_code)
        state["stages"][stage] = status
        if artifact:
            state.setdefault("artifacts", {})[stage] = artifact
        self.save(stock_code, state)
        return state

    def fail(self, stock_code: str, stage: str, error: Exception | str) -> None:
        state = self.load(stock_code) or self.start(stock_code)
        if stage in state.get("stages", {}):
            state["stages"][stage] = "failed"
        state["status"] = "failed"
        state["last_error"] = str(error)
        self.save(stock_code, state)

    def complete(self, stock_code: str, output_path: str) -> None:
        state = self.load(stock_code) or self.start(stock_code)
        state["status"] = "completed"
        state["output_path"] = output_path
        self.save(stock_code, state)

    def save_artifact(self, stock_code: str, name: str, payload: Dict) -> str:
        path = self.artifact_path(stock_code, name)
        atomic_write_json(path, payload)
        return str(path)

    def load_artifact(self, stock_code: str, name: str) -> Dict:
        return load_json(self.artifact_path(stock_code, name), {})
