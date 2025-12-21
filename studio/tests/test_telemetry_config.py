from studio.telemetry import configured_model_candidates


def test_configured_model_candidates_respects_priority(monkeypatch):
    monkeypatch.setenv("STUDIO_MODEL_PRIORITY", "gemini-2.5-pro,groq/mixtral-8x7b")
    monkeypatch.delenv("STUDIO_MODEL_CANDIDATES", raising=False)
    monkeypatch.delenv("STUDIO_MODEL", raising=False)
    monkeypatch.delenv("STUDIO_MODEL_FALLBACK", raising=False)
    monkeypatch.setenv("STUDIO_OLLAMA_MODEL", "ollama/llama3.1:8b")

    candidates = configured_model_candidates()

    assert candidates == [
        "gemini-2.5-pro",
        "groq/mixtral-8x7b",
        "ollama/llama3.1:8b",
    ]


def test_configured_model_candidates_deduplicates_and_appends(monkeypatch):
    monkeypatch.delenv("STUDIO_MODEL_PRIORITY", raising=False)
    monkeypatch.setenv("STUDIO_MODEL_CANDIDATES", "groq/mixtral-8x7b,gemini-2.5-pro")
    monkeypatch.setenv("STUDIO_MODEL", "gemini-2.5-pro")  # duplicate should be ignored
    monkeypatch.setenv("STUDIO_MODEL_FALLBACK", "groq/llama-3.1-70b")
    monkeypatch.setenv("STUDIO_OLLAMA_MODEL", "ollama/llama3.1:8b")

    candidates = configured_model_candidates()

    assert candidates == [
        "groq/mixtral-8x7b",
        "gemini-2.5-pro",
        "groq/llama-3.1-70b",
        "ollama/llama3.1:8b",
    ]
