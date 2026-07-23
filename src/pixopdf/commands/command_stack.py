from collections.abc import Callable

from .base import Command


class CommandStack:
    def __init__(self) -> None:
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._listeners: list[Callable[[], None]] = []
        self._clean_depth = 0

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def is_clean(self) -> bool:
        return self._clean_depth >= 0 and len(self._undo) == self._clean_depth

    def mark_clean(self) -> None:
        self._clean_depth = len(self._undo)

    def invalidate_clean(self) -> None:
        self._clean_depth = -1
        self._redo.clear()

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    def execute(self, command: Command) -> None:
        command.execute()
        if self._redo and self._clean_depth > len(self._undo):
            self._clean_depth = -1
        self._undo.append(command)
        self._redo.clear()
        self._notify()

    def undo(self) -> None:
        if not self._undo:
            return
        command = self._undo.pop()
        command.undo()
        self._redo.append(command)
        self._notify()

    def redo(self) -> None:
        if not self._redo:
            return
        command = self._redo.pop()
        command.execute()
        self._undo.append(command)
        self._notify()
