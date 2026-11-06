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

# Completion is defined POSITIVELY: an answer is complete only when the provider says it
# finished normally. Until 2026-11-06 it was defined negatively — only "the output budget ran
# out" counted as incomplete — so a non-empty answer stopped by a content filter, a refusal
# or a tool call was accepted as the block's translation. Every other reason the installed
# SDK can report (``openai.types.chat.chat_completion.Choice.finish_reason``,
# ``anthropic.types.stop_reason.StopReason``) is incomplete, with the reason kept verbatim
# in ``ModelResponse.stop_reason`` for the log. ``None`` is complete: a compatible provider
# that does not report a reason at all has not said the answer was cut off, and treating
# silence as truncation would retry every answer of such a provider.
# The Responses API reports completion as ``Response.status`` and is read by its own
# extractor, unchanged.
CHAT_COMPLETIONS_COMPLETE_FINISH_REASONS = frozenset({"stop"})
ANTHROPIC_COMPLETE_STOP_REASONS = frozenset({"end_turn", "stop_sequence"})


def chat_completion_finish_is_complete(finish_reason: object) -> bool:
    return finish_reason is None or (
        isinstance(finish_reason, str) and finish_reason in CHAT_COMPLETIONS_COMPLETE_FINISH_REASONS
    )


def anthropic_stop_is_complete(stop_reason: object) -> bool:
    return stop_reason is None or (
        isinstance(stop_reason, str) and stop_reason in ANTHROPIC_COMPLETE_STOP_REASONS
    )


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
