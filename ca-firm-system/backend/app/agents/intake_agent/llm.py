"""Optional LLM assistance for ambiguous columns. LiteLLM proxy only (OpenAI-compatible HTTP).

The model is asked to CHOOSE from a closed list of roles; it never produces numbers, dates or
rows. Output is validated against the allowed enum and confidence is capped, so a hallucinated
answer can at worst produce a wrong *suggestion* that is always marked for human review."""

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.agents.intake_agent.types import DOC_TYPES, ROLES

logger = logging.getLogger("app.intake.llm")
MAX_LLM_CONFIDENCE = 0.8  # LLM suggestions never outrank a confirmed or header-based match
MAX_COLUMNS = 40
MAX_SAMPLES = 5
MAX_CELL_CHARS = 60


@dataclass(frozen=True)
class ColumnQuery:
    index: int
    header: str | None
    samples: list[str]


@dataclass(frozen=True)
class ColumnAnswer:
    index: int
    role: str
    confidence: float


@dataclass(frozen=True)
class LlmResult:
    columns: list[ColumnAnswer]
    document_type: str | None
    model: str


class IntakeAssistant(Protocol):
    async def suggest(
        self, columns: list[ColumnQuery], category: str | None, doc_type_hint: str | None
    ) -> LlmResult | None: ...


def build_prompt(
    columns: list[ColumnQuery], category: str | None, doc_type_hint: str | None
) -> str:
    cols = [
        {
            "index": c.index,
            "header": (c.header or "")[:MAX_CELL_CHARS],
            "samples": [s[:MAX_CELL_CHARS] for s in c.samples[:MAX_SAMPLES]],
        }
        for c in columns[:MAX_COLUMNS]
    ]
    return (
        "You classify columns of a financial spreadsheet for an accounting firm. "
        "Choose, for each column, exactly one role from this list: "
        f"{', '.join(ROLES)}. Optionally choose document_type from: {', '.join(DOC_TYPES)}. "
        "Do NOT calculate, convert or invent any values. If unsure use role 'other' with low "
        'confidence. Respond with JSON only: {"document_type": str|null, "columns": '
        '[{"index": int, "role": str, "confidence": number 0-1}]}. '
        f"Uploader category: {category}. Heuristic guess: {doc_type_hint}. Columns: "
        + json.dumps(cols, ensure_ascii=False)
    )


def parse_response(text: str, allowed_indexes: set[int], model: str) -> LlmResult | None:
    """Validates model output; returns None if it is not usable. Unknown roles are dropped."""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        data: Any = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    answers: list[ColumnAnswer] = []
    for item in data.get("columns", []) if isinstance(data.get("columns"), list) else []:
        if not isinstance(item, dict):
            continue
        idx, role, conf = item.get("index"), item.get("role"), item.get("confidence")
        if (
            isinstance(idx, int) and not isinstance(idx, bool) and idx in allowed_indexes
            and role in ROLES and isinstance(conf, (int, float)) and not isinstance(conf, bool)
        ):  # fmt: skip
            answers.append(ColumnAnswer(idx, role, max(0.0, min(float(conf), MAX_LLM_CONFIDENCE))))
    dt = data.get("document_type")
    return LlmResult(answers, dt if dt in DOC_TYPES else None, model)


class LiteLlmAssistant:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._key, self._model, self._timeout = api_key, model, timeout

    async def suggest(
        self, columns: list[ColumnQuery], category: str | None, doc_type_hint: str | None
    ) -> LlmResult | None:
        if not columns:
            return None
        body = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "user", "content": build_prompt(columns, category, doc_type_hint)}
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    self._url, json=body, headers={"Authorization": f"Bearer {self._key}"}
                )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            logger.warning("llm assist unavailable: %s", type(exc).__name__)
            return None  # heuristics stand on their own
        return parse_response(str(text), {c.index for c in columns}, self._model)
