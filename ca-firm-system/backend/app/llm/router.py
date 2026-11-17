# ruff: noqa: E501
"""Local LiteLLM Python SDK Router with multi-key support, dynamic switching, and automatic fallbacks.

No proxy server is used. LiteLLM runs directly inside this application process via its Python SDK.
Features:
- Multi-API-Key Support: Supports multiple keys per provider for round-robin load balancing and automatic
  key-level failover upon rate limits (429) or transient provider errors.
- Dynamic Switching: Callers can dynamically switch models per agent, per task, or explicitly by alias.
- Automatic Fallback: Configures cross-model fallbacks (e.g. fast-general -> gemini-fast) and supports
  dynamic per-call fallback chains.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from litellm import Router

from app.core.config import Settings, get_settings
from app.llm.catalog import MODELS

logger = logging.getLogger("app.llm.router")

# Default model definitions mapping alias to provider and model identifier
DEFAULT_MODEL_DEFINITIONS: dict[str, dict[str, str]] = {
    "fast-general": {
        "model": "openai/gpt-4o-mini",
        "provider": "openai",
    },
    "strong-general": {
        "model": "openai/gpt-4o",
        "provider": "openai",
    },
    "claude-balanced": {
        "model": "anthropic/claude-sonnet-4-5",
        "provider": "anthropic",
    },
    "gemini-fast": {
        "model": "gemini/gemini-2.5-flash",
        "provider": "gemini",
    },
}

DEFAULT_FALLBACKS: list[dict[str, list[str]]] = [
    {"fast-general": ["gemini-fast", "claude-balanced", "strong-general"]},
    {"strong-general": ["claude-balanced", "gemini-fast", "fast-general"]},
    {"claude-balanced": ["strong-general", "fast-general", "gemini-fast"]},
    {"gemini-fast": ["fast-general", "claude-balanced", "strong-general"]},
]


def _find_config_file() -> Path | None:
    """Find infrastructure/litellm/config.yaml if present."""
    current = Path(__file__).resolve()
    for parent in [current.parents[2], current.parents[3]]:
        candidate = parent / "infrastructure" / "litellm" / "config.yaml"
        if candidate.is_file():
            return candidate
    return None


def build_model_list(
    settings: Settings,
    config_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Builds the deployment list for LiteLLM Router.

    Expands each model alias into multiple deployments when multiple API keys are provided,
    allowing automatic load-balancing and failover between keys.
    """
    model_definitions: dict[str, dict[str, Any]] = dict(DEFAULT_MODEL_DEFINITIONS)

    # If config.yaml exists, read underlying model targets
    cfg_file = config_path or _find_config_file()
    if cfg_file and cfg_file.is_file():
        try:
            with open(cfg_file, encoding="utf-8") as f:
                cfg_data = yaml.safe_load(f)
            if isinstance(cfg_data, dict) and "model_list" in cfg_data:
                for entry in cfg_data["model_list"]:
                    alias = entry.get("model_name")
                    params = entry.get("litellm_params", {})
                    target_model = params.get("model")
                    if alias and target_model and alias in MODELS:
                        provider = MODELS[alias].provider.lower()
                        model_definitions[alias] = {
                            "model": target_model,
                            "provider": provider,
                        }
        except Exception as exc:
            logger.warning("could not read litellm config file: %s", exc)

    deployments: list[dict[str, Any]] = []

    for alias, spec in MODELS.items():
        definition = model_definitions.get(alias)
        if not definition:
            continue

        target_model = definition["model"]
        provider = definition["provider"]
        keys = settings.get_provider_api_keys(provider)

        if keys:
            # Multi-key deployment: one deployment entry per key for this alias
            for idx, key in enumerate(keys):
                deployments.append(
                    {
                        "model_name": alias,
                        "litellm_params": {
                            "model": target_model,
                            "api_key": key,
                        },
                    }
                )
        else:
            # Fallback entry without explicit key (will use provider SDK env defaults if any)
            env_key = os.getenv(f"{provider.upper()}_API_KEY", "")
            deployments.append(
                {
                    "model_name": alias,
                    "litellm_params": {
                        "model": target_model,
                        "api_key": env_key or "placeholder-key",
                    },
                }
            )

    return deployments


class LocalLlmRouter:
    """Manages the in-process LiteLLM Router with multi-key and automatic fallback capabilities."""

    def __init__(
        self,
        settings: Settings,
        *,
        model_list: list[dict[str, Any]] | None = None,
        fallbacks: list[dict[str, list[str]]] | None = None,
    ) -> None:
        self._settings = settings
        self._model_list = model_list if model_list is not None else build_model_list(settings)
        self._fallbacks = fallbacks if fallbacks is not None else list(DEFAULT_FALLBACKS)

        self._router = Router(
            model_list=self._model_list,
            fallbacks=self._fallbacks,
            num_retries=settings.llm_max_retries,
            timeout=settings.llm_timeout_seconds,
            routing_strategy="round-robin",
        )
        logger.info(
            "Local LiteLLM Router initialized with %d deployments across %d aliases",
            len(self._model_list),
            len({d["model_name"] for d in self._model_list}),
        )

    @property
    def router(self) -> Router:
        return self._router

    def served_aliases(self) -> set[str]:
        """Returns the set of model aliases configured in the router."""
        return {d["model_name"] for d in self._model_list if "model_name" in d}

    def check_health(self) -> bool:
        """Readiness check verifying the local router is properly initialized."""
        return bool(self._model_list and self._router is not None)

    async def acompletion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        fallbacks: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Executes a completion using the local LiteLLM Router.

        Supports dynamic model selection and dynamic fallback chains.
        """
        call_kwargs = dict(kwargs)
        if fallbacks:
            call_kwargs["fallbacks"] = fallbacks
        return await self._router.acompletion(model=model, messages=messages, **call_kwargs)


# Global singleton router instance
_global_router: LocalLlmRouter | None = None


def get_local_router(settings: Settings | None = None) -> LocalLlmRouter:
    global _global_router
    if _global_router is None:
        s = settings or get_settings()
        _global_router = LocalLlmRouter(s)
    return _global_router


def reset_local_router() -> None:
    global _global_router
    _global_router = None
