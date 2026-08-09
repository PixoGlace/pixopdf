from collections.abc import Callable
from contextlib import suppress
from threading import Event
from typing import Any, cast

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class OperationSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    progress = Signal(object)
    cancelled = Signal()


class OperationContext:
    """Thread-safe progress and cooperative cancellation bridge for one task."""

    def __init__(self, signals: OperationSignals) -> None:
        self._signals = signals
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def report(self, progress: object) -> None:
        if not self.is_cancelled():
            with suppress(RuntimeError):
                self._signals.progress.emit(progress)


class OperationTask(QRunnable):
    """Run a blocking service call without freezing the Qt event loop."""

    def __init__(
        self,
        operation: Callable[[], Any] | Callable[[OperationContext], Any],
        *,
        contextual: bool = False,
    ) -> None:
        super().__init__()
        self.operation = operation
        self.signals = OperationSignals()
        self.context = OperationContext(self.signals)
        self.contextual = contextual

    def cancel(self) -> None:
        self.context.cancel()

    @Slot()
    def run(self) -> None:
        if self.context.is_cancelled():
            self.signals.cancelled.emit()
            return
        try:
            if self.contextual:
                operation = cast(Callable[[OperationContext], Any], self.operation)
                result = operation(self.context)
            else:
                operation_without_context = cast(Callable[[], Any], self.operation)
                result = operation_without_context()
        except Exception as exc:
            if self.context.is_cancelled():
                with suppress(RuntimeError):
                    self.signals.cancelled.emit()
            else:
                with suppress(RuntimeError):
                    self.signals.failed.emit(str(exc))
        else:
            with suppress(RuntimeError):
                if self.context.is_cancelled():
                    self.signals.cancelled.emit()
                else:
                    self.signals.succeeded.emit(result)
