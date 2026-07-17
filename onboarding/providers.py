"""Resume analysis provider protocol and bring-your-own-model configuration."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import requests

from config import TRACKER_DIR

_DEFAULT_SETTINGS_PATH = TRACKER_DIR / "onboarding" / "llm.json"
_DEFAULT_SECRET_PATH = TRACKER_DIR / "onboarding" / "llm.key"
_settings_path = _DEFAULT_SETTINGS_PATH
_secret_path = _DEFAULT_SECRET_PATH

_PROVIDER_DEFAULTS = {
    "local": {"base_url": "", "model": "Built-in local analyzer", "requires_api_key": False},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini", "requires_api_key": True},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "", "requires_api_key": True},
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "model": "llama3.2", "requires_api_key": False},
    "custom": {"base_url": "", "model": "", "requires_api_key": False},
}


@dataclass(frozen=True)
class ProviderSettings:
    provider: str
    base_url: str
    model: str
    requires_api_key: bool


class ResumeAnalyzer(Protocol):
    provider_name: str

    def analyze(self, resume_text: str) -> dict: ...


def set_provider_paths(settings_path: Path, secret_path: Path) -> None:
    """Override runtime provider paths (primarily for isolated tests)."""
    global _settings_path, _secret_path
    _settings_path = Path(settings_path)
    _secret_path = Path(secret_path)


def normalize_provider_settings(raw: dict) -> ProviderSettings:
    provider = str(raw.get("provider") or "local").strip().lower()
    if provider not in _PROVIDER_DEFAULTS:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    defaults = _PROVIDER_DEFAULTS[provider]
    base_url = str(raw.get("base_url") or defaults["base_url"]).strip().rstrip("/")
    model = str(raw.get("model") or defaults["model"]).strip()
    requires_key = bool(defaults["requires_api_key"])
    if provider == "custom":
        requires_key = bool(raw.get("requires_api_key", bool(raw.get("api_key"))))
    if provider != "local" and not base_url:
        raise ValueError("An OpenAI-compatible base URL is required")
    if provider != "local" and not model:
        raise ValueError("A model name is required")
    if provider != "local":
        parsed_url = urlsplit(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("The provider base URL must use http or https")
        if parsed_url.username or parsed_url.password:
            raise ValueError("The provider base URL must not contain credentials")
    return ProviderSettings(provider, base_url, model, requires_key)


class ProviderConfigStore:
    def __init__(self, settings_path: Path | None = None, secret_path: Path | None = None):
        self.settings_path = Path(settings_path or _settings_path)
        self.secret_path = Path(secret_path or _secret_path)

    def save(self, settings: ProviderSettings, *, api_key: str = "") -> dict:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(settings)
        self.settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if api_key:
            self.secret_path.parent.mkdir(parents=True, exist_ok=True)
            self.secret_path.write_text(api_key.strip(), encoding="utf-8")
            try:
                os.chmod(self.secret_path, 0o600)
            except OSError:
                pass
        elif settings.provider in {"local", "ollama"} and self.secret_path.exists():
            self.secret_path.unlink()
        return self.public_settings()

    def load(self) -> ProviderSettings:
        if not self.settings_path.exists():
            return normalize_provider_settings({"provider": "local"})
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError("Saved LLM settings are invalid") from exc
        return normalize_provider_settings(raw)

    def api_key(self) -> str:
        if not self.secret_path.exists():
            return ""
        return self.secret_path.read_text(encoding="utf-8").strip()

    def public_settings(self) -> dict:
        settings = self.load()
        return {
            "provider": settings.provider,
            "base_url": settings.base_url,
            "model": settings.model,
            "requires_api_key": settings.requires_api_key,
            "has_api_key": bool(self.api_key()),
        }


_ROLE_ACRONYMS = {
    "Ai": "AI",
    "Api": "API",
    "Genai": "GenAI",
    "Llm": "LLM",
    "Ml": "ML",
    "Nlp": "NLP",
    "Rag": "RAG",
}


def _unique_strings(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        item = str(value).strip()
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _pretty_role(role: str) -> str:
    return " ".join(_ROLE_ACRONYMS.get(word, word) for word in role.title().split())


class LocalResumeAnalyzer:
    provider_name = "local"

    def analyze(self, resume_text: str) -> dict:
        from resume.resume_profile import extract_profile_from_text

        extracted = extract_profile_from_text(resume_text)
        roles = _unique_strings(
            _pretty_role(role) for role in extracted.get("roles") or []
        )
        suggested = [
            {
                "title": role,
                "confidence": max(0.58, 0.86 - index * 0.08),
                "reason": "This role is supported by titles, skills, or project evidence in your resume.",
            }
            for index, role in enumerate(roles[:5])
        ]
        return {
            "name": _candidate_name(resume_text),
            "headline": "Resume-based career profile",
            "summary": "Built locally from the skills, roles, projects, and preferences visible in your resume.",
            "roles": [item["title"] for item in suggested] or roles,
            "suggested_roles": suggested,
            "skills": _unique_strings(extracted.get("skills") or []),
            "projects": list(extracted.get("projects") or []),
            "locations": _unique_strings(extracted.get("locations") or []),
            "experience_level": extracted.get("experience_level") or "entry_level",
            "years_experience": extracted.get("years_experience"),
            "work_modes": _unique_strings(extracted.get("work_modes") or []),
            "visa_needed": extracted.get("visa_needed"),
            "missing": list(extracted.get("missing") or []),
            "source": "local",
        }


def _candidate_name(text: str) -> str:
    for line in str(text or "").splitlines()[:5]:
        candidate = line.strip()
        if (
            2 <= len(candidate.split()) <= 5
            and "@" not in candidate
            and not any(char.isdigit() for char in candidate)
            and len(candidate) <= 70
        ):
            return candidate
    return "Candidate"


_ANALYSIS_SCHEMA = {
    "name": "Candidate name if present",
    "headline": "One short, evidence-based professional headline",
    "summary": "Two sentences describing demonstrated work",
    "roles": ["roles explicitly supported by the resume"],
    "suggested_roles": [
        {"title": "role", "confidence": 0.0, "reason": "specific resume evidence"}
    ],
    "skills": ["skills explicitly present"],
    "projects": [{"name": "project", "evidence": "what was built"}],
    "locations": ["locations explicitly present"],
    "experience_level": "entry_level | mid_level | senior",
    "years_experience": None,
    "work_modes": ["remote | hybrid | onsite"],
    "visa_needed": None,
    "missing": ["important facts the resume cannot establish"],
}


def _provider_error_message(exc: requests.RequestException) -> str:
    if isinstance(exc, requests.Timeout):
        return "The provider timed out. Check the endpoint or try again."
    if isinstance(exc, requests.ConnectionError):
        return "Opportune could not reach the provider. Check the endpoint and network."
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in {401, 403}:
        return "The provider rejected the connection. Check the API key and endpoint."
    if status == 404:
        return "The provider model or endpoint was not found. Check both settings."
    if status == 429:
        return "The provider is rate-limiting requests. Wait and try again."
    if isinstance(status, int) and status >= 500:
        return "The provider is temporarily unavailable. Try again later."
    if isinstance(status, int):
        return f"The provider request failed (HTTP {status}). Check the provider settings."
    return "The provider request failed. Check the endpoint and provider settings."


def _provider_request(method, url: str, **kwargs):
    try:
        response = method(url, **kwargs)
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise ValueError(_provider_error_message(exc)) from None


class OpenAICompatibleAnalyzer:
    def __init__(self, settings: ProviderSettings, api_key: str = "", timeout: int = 90):
        self.settings = settings
        self.api_key = api_key
        self.timeout = max(2, min(int(timeout), 120))
        self.provider_name = settings.provider

    def analyze(self, resume_text: str) -> dict:
        if self.settings.requires_api_key and not self.api_key:
            raise ValueError("This provider needs an API key. Add it before analyzing your resume.")
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        prompt = (
            "Analyze this sanitized resume for job-search onboarding. Use only evidence in the resume; "
            "never invent skills, years, authorization, or locations. Return one JSON object matching "
            f"this shape: {json.dumps(_ANALYSIS_SCHEMA)}. Suggest at most five realistic roles and explain "
            "each suggestion with concrete evidence. Use null when a fact cannot be known.\n\nRESUME:\n"
            + resume_text
        )
        response = _provider_request(
            requests.post,
            f"{self.settings.base_url}/chat/completions",
            headers=headers,
            json={
                "model": self.settings.model,
                "temperature": 0.1,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a precise career evidence analyst. Return JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=self.timeout,
        )
        try:
            content = response.json()["choices"][0]["message"]["content"]
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
            result = json.loads(content)
            return _normalize_analysis(result, source=self.settings.provider)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError("The model returned an invalid resume analysis. Try again or choose another model.") from exc


def _normalize_analysis(raw: dict, *, source: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Resume analysis must be a JSON object")
    roles = [str(item).strip() for item in raw.get("roles") or [] if str(item).strip()]
    suggestions = []
    for item in raw.get("suggested_roles") or []:
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            continue
        confidence = float(item.get("confidence") or 0)
        suggestions.append(
            {
                "title": str(item["title"]).strip(),
                "confidence": max(0.0, min(confidence, 1.0)),
                "reason": str(item.get("reason") or "Supported by resume evidence.").strip(),
            }
        )
    if not suggestions:
        suggestions = [
            {"title": role, "confidence": 0.65, "reason": "Supported by resume evidence."}
            for role in roles[:5]
        ]
    return {
        "name": str(raw.get("name") or "Candidate").strip(),
        "headline": str(raw.get("headline") or "Resume-based career profile").strip(),
        "summary": str(raw.get("summary") or "").strip(),
        "roles": roles or [item["title"] for item in suggestions],
        "suggested_roles": suggestions[:5],
        "skills": [str(item).strip() for item in raw.get("skills") or [] if str(item).strip()],
        "projects": [item for item in raw.get("projects") or [] if isinstance(item, dict)],
        "locations": [str(item).strip() for item in raw.get("locations") or [] if str(item).strip()],
        "experience_level": str(raw.get("experience_level") or "entry_level").strip(),
        "years_experience": raw.get("years_experience"),
        "work_modes": [str(item).strip().lower() for item in raw.get("work_modes") or [] if str(item).strip()],
        "visa_needed": raw.get("visa_needed") if isinstance(raw.get("visa_needed"), bool) else None,
        "missing": [str(item).strip() for item in raw.get("missing") or [] if str(item).strip()],
        "source": source,
    }


def build_analyzer(store: ProviderConfigStore | None = None) -> ResumeAnalyzer:
    store = store or ProviderConfigStore()
    settings = store.load()
    if settings.provider == "local":
        return LocalResumeAnalyzer()
    return OpenAICompatibleAnalyzer(settings, api_key=store.api_key())


def test_provider_connection(store: ProviderConfigStore | None = None) -> dict:
    store = store or ProviderConfigStore()
    settings = store.load()
    if settings.provider == "local":
        return {"ok": True, "message": "Built-in local analysis is ready."}
    if settings.requires_api_key and not store.api_key():
        raise ValueError("Add an API key before testing this provider.")
    headers = {}
    if store.api_key():
        headers["authorization"] = f"Bearer {store.api_key()}"
    _provider_request(
        requests.get,
        f"{settings.base_url}/models",
        headers=headers,
        timeout=15,
    )
    return {"ok": True, "message": f"Connected to {settings.provider}.", "model": settings.model}
