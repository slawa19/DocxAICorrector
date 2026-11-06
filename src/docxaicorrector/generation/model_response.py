"""One shape for a model's answer, and one exception type per way it can fail to be one.

Three provider APIs serve text generation — Responses, Chat Completions and Anthropic
Messages — and each reports "the answer was cut off" in its own field. Until spec 061 only
the Responses path read that field, so the same truncated answer was retried on one path
and accepted as a translation on the other two. ``ModelResponse`` is what every extractor
produces, so the question "is this answer complete?" is asked once, the same way, for all
three.

The failure classes used to be recognised by a substring of a ``RuntimeError`` message,
which is how ``collapsed_output`` came to be retried by one predicate and missed by the
next one, escaping as an exception where ``empty_response`` took a controlled fallback.
They are types now. Each one still subclasses ``RuntimeError`` and still carries its code
in the message, so ``except RuntimeError`` callers and log readers see what they saw
before; only the code that SELECTS a branch changed from reading text to reading a type.
"""

from __future__ import annotations

from dataclasses import dataclass

API_PATH_RESPONSES = "responses"
API_PATH_CHAT_COMPLETIONS = "chat_completions"
API_PATH_ANTHROPIC_MESSAGES = "anthropic"

# The verbatim provider values that mean "the output budget ran out". Read from the
# installed SDK types, not guessed: ``openai.types.chat.chat_completion.Choice.finish_reason``
# and ``anthropic.types.stop_reason.StopReason``. The Responses API reports it as
# ``Response.status == "incomplete"`` instead, which its extractor reads directly.
CHAT_COMPLETIONS_TRUNCATED_FINISH_REASON = "length"
# Anthropic has TWO: ``max_tokens`` (the requested output budget ran out) and
# ``model_context_window_exceeded`` (prompt plus output hit the model's context window, so
# generation stopped mid-answer). The second was not read until 2026-11-06 and a cut-off
# answer with intact markers was accepted as a translation. Both mean "the text stops
# early"; the attempt loop treats them alike, and the degradation ladder — which asks for
# less at a time — is the remedy that also fits the second one.
ANTHROPIC_TRUNCATED_STOP_REASONS = frozenset({"max_tokens", "model_context_window_exceeded"})


@dataclass(frozen=True)
class ModelResponse:
    """What one provider call answered, in the form the attempt loop reasons about.

    ``text`` is the normalised markdown. ``incomplete`` says the provider stopped because
    the output budget ran out, whichever field it used to say so. ``stop_reason`` is the
    provider's own reason string, verbatim, when it reported one — diagnostic only.
    """

    text: str
    incomplete: bool = False
    stop_reason: str | None = None


class ModelResponseError(RuntimeError):
    """The model answered, but not with something the pipeline can use as the block."""

    error_code = "model_response_error"


class EmptyResponse(ModelResponseError):
    error_code = "empty_response"


class CollapsedOutput(ModelResponseError):
    """There was text, and nothing was left of it after normalisation (an empty fence)."""

    error_code = "collapsed_output"


class IncompleteResponse(ModelResponseError):
    error_code = "incomplete_response"


class NonCompletedResponse(ModelResponseError):
    """The Responses API reported a status that is neither ``completed`` nor ``incomplete``."""

    error_code = "non_completed_response"
