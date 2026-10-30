"""The system under test: one structured-output call that screens a CIM.

The call returns a ScreenResult whatever happened, so the harness can tell a
model outcome (ok, refused, truncated, malformed) from a plumbing failure
(which raises). Retries are done here rather than inside the SDK so the
attempt count is recorded per row.
"""

import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from pydantic import ValidationError

from .schema import Screen

DEFAULT_MODEL = "claude-opus-5-5"
PROMPTS_DIR = Path(__file__).parent / "prompts"
OUTPUT_SCHEMA = anthropic.transform_schema(Screen)

RETRYABLE = (
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.APIConnectionError,  # includes APITimeoutError
)


class ServedModelMismatch(RuntimeError):
    """The API answered with a different model than the one requested."""


@dataclass
class ScreenResult:
    status: str  # ok | truncated | refusal | invalid_output
    screen: Screen | None
    raw_text: str
    stop_reason: str | None
    served_model: str
    usage: dict
    latency_s: float  # final successful request only, excludes backoff
    attempts: int
    request_id: str | None = None
    error: str | None = None
    refusal_category: str | None = None
    extra: dict = field(default_factory=dict)


def load_prompt(version: str) -> str:
    return (PROMPTS_DIR / f"{version}.md").read_text()


def build_request(document: str, prompt_version: str, model: str, effort: str) -> dict:
    return {
        "model": model,
        "max_tokens": 16000,
        "system": load_prompt(prompt_version),
        "messages": [
            {
                "role": "user",
                "content": f"<document>\n{document}\n</document>\n\nScreen this CIM.",
            }
        ],
        "output_config": {
            "effort": effort,
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
    }


def screen(
    document: str,
    *,
    prompt_version: str = "v2",
    model: str = DEFAULT_MODEL,
    effort: str = "medium",
    client: anthropic.Anthropic | None = None,
    max_attempts: int = 4,
) -> ScreenResult:
    client = client or anthropic.Anthropic(max_retries=0, timeout=300.0)
    request = build_request(document, prompt_version, model, effort)

    for attempt in range(1, max_attempts + 1):
        started = time.monotonic()
        try:
            response = client.messages.create(**request)
            break
        except RETRYABLE:
            if attempt == max_attempts:
                raise
            time.sleep(min(2**attempt + random.uniform(0, 1), 30))
    latency = time.monotonic() - started

    if response.model != model:
        raise ServedModelMismatch(f"requested {model}, served {response.model}")

    usage = {
        k: getattr(response.usage, k, 0) or 0
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    }
    text = "".join(b.text for b in response.content if b.type == "text")
    base = dict(
        raw_text=text,
        stop_reason=response.stop_reason,
        served_model=response.model,
        usage=usage,
        latency_s=round(latency, 2),
        attempts=attempt,
        request_id=response._request_id,
    )

    if response.stop_reason == "refusal":
        details = response.stop_details
        return ScreenResult(
            status="refusal",
            screen=None,
            refusal_category=getattr(details, "category", None) if details else None,
            **base,
        )
    if response.stop_reason == "max_tokens":
        return ScreenResult(status="truncated", screen=None, **base)
    try:
        return ScreenResult(status="ok", screen=Screen.model_validate_json(text), **base)
    except ValidationError as e:
        return ScreenResult(status="invalid_output", screen=None, error=str(e)[:2000], **base)
