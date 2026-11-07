"""Errors raised by the LLM gateway. Messages are user-safe: no provider names, URLs or keys."""


class LlmError(Exception):
    code = "llm_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ModelUnavailableError(LlmError):
    """No approved, enabled, capable model is configured for the task (nothing was sent)."""

    code = "model_unavailable"


class InputTooLargeError(LlmError):
    code = "input_too_large"


class LlmCallFailedError(LlmError):
    """The gateway/provider failed after bounded retries (and the configured fallback, if any)."""

    code = "llm_call_failed"
