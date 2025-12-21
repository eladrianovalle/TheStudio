from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, Optional

try:
    import litellm
    from litellm.integrations.custom_logger import CustomLogger
except Exception:  # pragma: no cover - liteLLM always available in prod, but guard for tests
    litellm = None

    class CustomLogger:  # type: ignore
        pass


RATE_LIMIT_WARN_RATIO = float(os.environ.get("STUDIO_RATE_LIMIT_WARN_RATIO", "0.2"))
COOLDOWN_MIN_SECONDS = 5
COOLDOWN_DEFAULT_SECONDS = 30
OVERHEAT_COOLDOWN_SECONDS = int(os.environ.get("STUDIO_OVERHEAT_COOLDOWN_SECONDS", "45"))
OVERHEAT_STATUS_CODES = {
    code.strip()
    for code in os.environ.get("STUDIO_OVERHEAT_STATUS_CODES", "500,502,503,504").split(",")
    if code.strip()
}


@dataclass
class RateLimitSnapshot:
    model: str
    remaining_requests: Optional[int] = None
    limit_requests: Optional[int] = None
    remaining_tokens: Optional[int] = None
    limit_tokens: Optional[int] = None
    reset_requests: Optional[str] = None
    reset_tokens: Optional[str] = None
    retry_after: Optional[int] = None
    low_headroom: bool = False
    last_updated: float = field(default_factory=time.time)


class RateLimitMonitor:
    def __init__(self, warn_ratio: float = RATE_LIMIT_WARN_RATIO):
        self._warn_ratio = warn_ratio
        self._snapshots: Dict[str, RateLimitSnapshot] = {}
        self._lock = threading.Lock()

    def _parse_int(self, value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _should_warn(self, remaining: Optional[int], limit: Optional[int]) -> bool:
        if not remaining or not limit:
            return False
        if limit <= 0:
            return False
        return (remaining / limit) <= self._warn_ratio

    def update(self, model: Optional[str], headers: Dict[str, str]):
        if not model or not headers:
            return

        normalized = {k.lower(): v for k, v in headers.items()}
        snapshot = RateLimitSnapshot(
            model=model,
            remaining_requests=self._parse_int(normalized.get("x-ratelimit-remaining-requests")),
            limit_requests=self._parse_int(normalized.get("x-ratelimit-limit-requests")),
            remaining_tokens=self._parse_int(normalized.get("x-ratelimit-remaining-tokens")),
            limit_tokens=self._parse_int(normalized.get("x-ratelimit-limit-tokens")),
            reset_requests=normalized.get("x-ratelimit-reset-requests"),
            reset_tokens=normalized.get("x-ratelimit-reset-tokens"),
            retry_after=self._parse_int(normalized.get("retry-after")),
        )

        snapshot.low_headroom = any(
            [
                self._should_warn(snapshot.remaining_requests, snapshot.limit_requests),
                self._should_warn(snapshot.remaining_tokens, snapshot.limit_tokens),
            ]
        )
        snapshot.last_updated = time.time()

        with self._lock:
            previous = self._snapshots.get(model)
            self._snapshots[model] = snapshot

        if snapshot.low_headroom and (not previous or not previous.low_headroom):
            warn_msg = (
                f"[RateLimit] {model} nearing quota. Remaining "
                f"requests: {snapshot.remaining_requests}/{snapshot.limit_requests}, "
                f"tokens: {snapshot.remaining_tokens}/{snapshot.limit_tokens}"
            )
            print(warn_msg, file=sys.stderr)

    def snapshot(self) -> Dict[str, Dict]:
        with self._lock:
            return {model: asdict(snapshot) for model, snapshot in self._snapshots.items()}

    def is_low_headroom(self, model: str) -> bool:
        with self._lock:
            snapshot = self._snapshots.get(model)
            return bool(snapshot and snapshot.low_headroom)

    def last_retry_after(self, model: str) -> Optional[int]:
        with self._lock:
            snapshot = self._snapshots.get(model)
            return snapshot.retry_after if snapshot else None

    def reset(self):
        with self._lock:
            self._snapshots.clear()


def _parse_model_list(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    parts = [segment.strip() for segment in raw.split(",")]
    return [p for p in parts if p]


def configured_model_candidates() -> list[str]:
    priority = _parse_model_list(os.environ.get("STUDIO_MODEL_PRIORITY"))
    candidates = priority or _parse_model_list(os.environ.get("STUDIO_MODEL_CANDIDATES"))
    primary = os.environ.get("STUDIO_MODEL")
    fallback = _parse_model_list(os.environ.get("STUDIO_MODEL_FALLBACK"))
    local_model = os.environ.get("STUDIO_OLLAMA_MODEL", "ollama/llama3.1:8b")

    ordered = []
    for entry in (candidates + ([primary] if primary else []) + fallback):
        if entry and entry not in ordered:
            ordered.append(entry)

    if local_model and local_model not in ordered:
        ordered.append(local_model)

    return ordered or ["gemini-2.5-flash"]


class ModelManager:
    def __init__(self, monitor: RateLimitMonitor):
        self._monitor = monitor
        self._candidates: list[str] = []
        self._cooldowns: Dict[str, float] = {}
        self._overheated: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._last_selected: Optional[str] = None

    def configure_candidates(self, ordered_models: list[str]):
        canonical = ordered_models or ["gemini-2.5-flash"]
        with self._lock:
            self._candidates = canonical

    def mark_cooldown(
        self,
        model: Optional[str],
        retry_after: Optional[int],
        reason: str = "rate_limit",
    ):
        if not model:
            return
        duration = retry_after or self._monitor.last_retry_after(model) or COOLDOWN_DEFAULT_SECONDS
        duration = max(duration, COOLDOWN_MIN_SECONDS)
        with self._lock:
            self._cooldowns[model] = time.time() + duration
        print(
            f"[ModelHealth] Cooling down {model} for {duration}s ({reason}).",
            file=sys.stderr,
        )

    def mark_overheated(
        self,
        model: Optional[str],
        reason: str = "overheated",
        cooldown_seconds: Optional[int] = None,
    ):
        if not model:
            return
        duration = cooldown_seconds or OVERHEAT_COOLDOWN_SECONDS
        duration = max(duration, COOLDOWN_MIN_SECONDS)
        with self._lock:
            self._overheated[model] = time.time() + duration
        print(
            f"[ModelHealth] Marking {model} as hot for {duration}s ({reason}).",
            file=sys.stderr,
        )

    def _available_candidates(self, now: float) -> list[str]:
        return [
            model
            for model in self._candidates
            if self._cooldowns.get(model, 0) <= now
            and self._overheated.get(model, 0) <= now
        ]

    def select_model(self) -> str:
        with self._lock:
            candidates = list(self._candidates)
        now = time.time()
        available = self._available_candidates(now) or candidates
        preferred = [m for m in available if not self._monitor.is_low_headroom(m)]
        choice = preferred[0] if preferred else available[0]
        with self._lock:
            self._last_selected = choice
        return choice

    def serialize(self) -> Dict[str, Dict]:
        return {
            "candidates": list(self._candidates),
            "cooldowns": self._cooldowns.copy(),
            "overheated": self._overheated.copy(),
            "current": self._last_selected,
        }

    def current_model(self) -> Optional[str]:
        with self._lock:
            return self._last_selected

    def is_overheated(self, model: str) -> bool:
        with self._lock:
            until = self._overheated.get(model)
            return bool(until and until > time.time())

    def reset(self):
        with self._lock:
            self._cooldowns.clear()
            self._overheated.clear()
            self._candidates = []
            self._last_selected = None


rate_limit_monitor = RateLimitMonitor()
model_manager = ModelManager(rate_limit_monitor)
_callback_registered = False


class LiteLLMRateLimitCallback(CustomLogger):
    def _extract_headers(self, kwargs, response_obj) -> Dict[str, str]:
        headers = kwargs.get("response_headers")
        if headers:
            return headers

        candidate_attrs = [
            "response_headers",
            "headers",
        ]
        for attr in candidate_attrs:
            value = getattr(response_obj, attr, None)
            if value:
                return value

        if isinstance(response_obj, dict):
            for key in candidate_attrs:
                if key in response_obj:
                    return response_obj[key]
        return {}

    def _handle_headers(self, kwargs, response_obj):
        model = kwargs.get("model")
        headers = self._extract_headers(kwargs, response_obj)
        if headers:
            rate_limit_monitor.update(model, headers)
        return model, headers

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._handle_headers(kwargs, response_obj)

    async def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        model, headers = self._handle_headers(kwargs, response_obj)
        exception = kwargs.get("exception")
        status_code = getattr(exception, "status_code", None) if exception else None
        status_code = status_code or getattr(exception, "status", None) if exception else None
        if not status_code and response_obj is not None:
            status_code = getattr(response_obj, "status_code", None)
        try:
            status_int = int(status_code) if status_code is not None else None
        except (TypeError, ValueError):
            status_int = None

        if status_int == 429:
            retry_after = headers.get("retry-after")
            retry_after_int = None
            try:
                retry_after_int = int(retry_after) if retry_after else None
            except (TypeError, ValueError):
                retry_after_int = None
            model_manager.mark_cooldown(model, retry_after_int, reason="rate_limit")
            return

        exception_message = str(exception).lower() if exception else ""
        if status_int and str(status_int) in OVERHEAT_STATUS_CODES:
            model_manager.mark_overheated(
                model, reason=f"HTTP {status_int} failure"
            )
        elif any(token in exception_message for token in ("temperature", "overloaded", "busy")):
            model_manager.mark_overheated(
                model, reason=f"provider reported {exception_message[:60]}"
            )


def register_litellm_callback():
    global _callback_registered
    if _callback_registered or litellm is None:
        return
    callback = LiteLLMRateLimitCallback()
    existing = getattr(litellm, "callbacks", None)
    if existing is None:
        litellm.callbacks = [callback]
    else:
        if not any(isinstance(cb, LiteLLMRateLimitCallback) for cb in existing):
            existing.append(callback)
    _callback_registered = True
    return callback


# Configure candidates + register callback at import time for convenience
model_manager.configure_candidates(configured_model_candidates())
register_litellm_callback()


def reset_telemetry_state_for_tests():
    rate_limit_monitor.reset()
    model_manager.reset()
