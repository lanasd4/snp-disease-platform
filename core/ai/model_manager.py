"""
AI Model Management (Ollama)
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import re
import subprocess
import socket
import time
import urllib.parse
import urllib.request
from core.paths import get_project_root


DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9._-]+)?$")


def get_config_path() -> Path:
    return get_project_root() / "data" / "metadata" / "ai_model_config.json"


def read_config() -> Dict[str, Any]:
    path = get_config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_config(config: Dict[str, Any]) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_model_name(model_name: str) -> bool:
    model_name = str(model_name or "").strip()
    return bool(model_name and MODEL_NAME_PATTERN.fullmatch(model_name))


PROBE_TIMEOUT_S = 0.4
PROBE_CACHE_S = 30.0
_probe_cache: Dict[str, tuple] = {}


def ollama_reachable(base_url: str = DEFAULT_OLLAMA_BASE_URL) -> bool:
    """Fast check that something listens on the Ollama port (cached for 30 s)."""
    now = time.monotonic()
    cached = _probe_cache.get(base_url)
    if cached and now - cached[0] < PROBE_CACHE_S:
        return cached[1]
    parsed = urllib.parse.urlparse(base_url)
    host = "127.0.0.1" if parsed.hostname in (None, "localhost") else parsed.hostname
    try:
        with socket.create_connection((host, parsed.port or 11434), timeout=PROBE_TIMEOUT_S):
            reachable = True
    except OSError:
        reachable = False
    _probe_cache[base_url] = (now, reachable)
    return reachable


def _request_json(url: str, timeout: int = 4) -> Dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if not ollama_reachable(f"{parsed.scheme}://{parsed.netloc}"):
        raise ConnectionError("Ollama is not running.")
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    return json.loads(raw)


def get_ollama_status(base_url: str = DEFAULT_OLLAMA_BASE_URL) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        payload = _request_json(base_url.rstrip("/") + "/api/tags", timeout=4)
        models = payload.get("models", [])
        return {
            "running": True,
            "status": "Running",
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "error": "",
            "raw_model_count": len(models),
        }
    except Exception as exc:
        return {
            "running": False,
            "status": "Stopped",
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "error": str(exc),
            "raw_model_count": 0,
        }


def list_installed_models(base_url: str = DEFAULT_OLLAMA_BASE_URL) -> List[Dict[str, Any]]:
    try:
        payload = _request_json(base_url.rstrip("/") + "/api/tags", timeout=5)
    except Exception:
        return []

    rows = []
    for item in payload.get("models", []):
        details = item.get("details", {}) or {}
        name = str(item.get("name") or item.get("model") or "").strip()
        if not name:
            continue
        rows.append({
            "name": name,
            "family": details.get("family", ""),
            "families": ", ".join(details.get("families", []) or []),
            "parameters": details.get("parameter_size", ""),
            "quantization": details.get("quantization_level", ""),
            "size_bytes": item.get("size", 0),
            "size": format_size(item.get("size", 0)),
            "modified_at": item.get("modified_at", ""),
            "context_length": "",
            "status": "Installed",
        })
    return rows


def format_size(size_bytes: Any) -> str:
    try:
        value = float(size_bytes)
    except Exception:
        return ""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def get_active_model() -> Optional[str]:
    config = read_config()
    model = str(config.get("active_model", "")).strip()
    return model or None


def set_active_model(model_name: str) -> Dict[str, Any]:
    model_name = str(model_name or "").strip()
    if not validate_model_name(model_name):
        return {"ok": False, "message": "Invalid model name."}

    installed = {item["name"] for item in list_installed_models()}
    if model_name not in installed:
        return {"ok": False, "message": "Model is not installed locally."}

    config = read_config()
    config.update({
        "active_model": model_name,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "storage": "data/metadata/ai_model_config.json",
    })
    write_config(config)
    return {"ok": True, "message": f"Active model updated to {model_name}."}


def test_model(model_name: str, base_url: str = DEFAULT_OLLAMA_BASE_URL) -> Dict[str, Any]:
    model_name = str(model_name or "").strip()
    if not validate_model_name(model_name):
        return {"ok": False, "elapsed_seconds": 0, "message": "Invalid model name.", "response": ""}

    start = time.perf_counter()
    url = base_url.rstrip("/") + "/api/chat"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "Answer briefly as an educational bioinformatics assistant."},
            {"role": "user", "content": "Explain what SNP means in one short sentence."},
        ],
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.1,
            "top_p": 0.7,
            "top_k": 25,
            "num_ctx": 1024,
            "num_predict": 80,
            "seed": 42,
        },
    }
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8", errors="ignore")
        result = json.loads(raw)
        content = str(result.get("message", {}).get("content", "")).strip()
        return {
            "ok": bool(content),
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "message": "Working" if content else "No response content.",
            "response": content,
        }
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "message": str(exc),
            "response": "",
        }


def install_model(model_name: str) -> Dict[str, Any]:
    model_name = str(model_name or "").strip()
    if not validate_model_name(model_name):
        return {"ok": False, "message": "Invalid model name.", "output": ""}

    installed = {item["name"] for item in list_installed_models()}
    if model_name in installed:
        return {"ok": False, "message": "Model is already installed.", "output": ""}

    try:
        completed = subprocess.run(
            ["ollama", "pull", model_name],
            cwd=str(get_project_root()),
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        return {
            "ok": completed.returncode == 0,
            "message": "Installation completed." if completed.returncode == 0 else "Installation failed.",
            "output": output.strip(),
        }
    except FileNotFoundError:
        return {"ok": False, "message": "Ollama executable was not found.", "output": ""}
    except Exception as exc:
        return {"ok": False, "message": str(exc), "output": ""}
