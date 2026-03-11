from dataclasses import dataclass


@dataclass(frozen=True)
class SetStateEvent:
    values: dict[str, object]


@dataclass(frozen=True)
class ResetImageStateEvent:
    pass


@dataclass(frozen=True)
class SetProcessingStatusEvent:
    payload: dict[str, object]


@dataclass(frozen=True)
class FinalizeProcessingStatusEvent:
    stage: str
    detail: str
    progress: float


@dataclass(frozen=True)
class PushActivityEvent:
    message: str


@dataclass(frozen=True)
class AppendLogEvent:
    payload: dict[str, object]


@dataclass(frozen=True)
class AppendImageLogEvent:
    payload: dict[str, object]


@dataclass(frozen=True)
class WorkerCompleteEvent:
    outcome: str


@dataclass(frozen=True)
class PreparationCompleteEvent:
    prepared_run_context: object
    upload_marker: str


@dataclass(frozen=True)
class PreparationFailedEvent:
    upload_marker: str
    error_message: str


ProcessingEvent = (
    SetStateEvent
    | ResetImageStateEvent
    | SetProcessingStatusEvent
    | FinalizeProcessingStatusEvent
    | PushActivityEvent
    | AppendLogEvent
    | AppendImageLogEvent
    | WorkerCompleteEvent
    | PreparationCompleteEvent
    | PreparationFailedEvent
)