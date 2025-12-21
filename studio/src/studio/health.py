import os
from typing import List, Tuple

import requests


OLLAMA_HEALTH_TIMEOUT = float(os.environ.get("STUDIO_OLLAMA_HEALTH_TIMEOUT", "2.5"))


def _normalize_base_url(base_url: str) -> str:
    if not base_url:
        return "http://localhost:11434"
    return base_url.rstrip("/")


def _ollama_model_name(candidate: str) -> str:
    return candidate.split("/", 1)[1] if "/" in candidate else candidate


def _fetch_ollama_tags(base_url: str) -> List[str]:
    response = requests.get(f"{base_url}/api/tags", timeout=OLLAMA_HEALTH_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    models = payload.get("models") or payload.get("tags") or []
    names = []
    for entry in models:
        if isinstance(entry, dict):
            name = entry.get("name") or entry.get("model")
            if name:
                names.append(name)
        elif isinstance(entry, str):
            names.append(entry)
    return names


def check_ollama_health(candidate: str, base_url: str) -> Tuple[bool, str]:
    """Return (healthy, detail) for the requested Ollama model."""
    normalized_url = _normalize_base_url(base_url)
    requested_model = _ollama_model_name(candidate)

    try:
        available = _fetch_ollama_tags(normalized_url)
    except requests.RequestException as exc:
        return False, f"Ollama unreachable at {normalized_url}: {exc}"
    except ValueError:
        return False, "Invalid response from Ollama tags endpoint"

    if requested_model not in available:
        return (
            False,
            f"Ollama missing model '{requested_model}'. Install it via `ollama pull {requested_model}`.",
        )

    try:
        version_response = requests.get(
            f"{normalized_url}/api/version", timeout=OLLAMA_HEALTH_TIMEOUT
        )
        version_response.raise_for_status()
        version_payload = version_response.json()
        version = version_payload.get("version")
    except requests.RequestException:
        version = None
    except ValueError:
        version = None

    detail = f"Ollama ready ({'v' + version if version else 'version unknown'})"
    return True, detail


__all__ = ["check_ollama_health"]
