from PySide6.QtWidgets import QApplication

from pixopdf.ui.workspace.operation_worker import OperationContext, OperationTask


def test_contextual_operation_reports_progress_and_succeeds(qapp: QApplication) -> None:
    progress: list[object] = []
    results: list[object] = []
    task = OperationTask(
        lambda context: (context.report(42), "done")[1],
        contextual=True,
    )
    task.signals.progress.connect(progress.append)
    task.signals.succeeded.connect(results.append)

    task.run()
    qapp.processEvents()

    assert progress == [42]
    assert results == ["done"]


def test_cancelled_contextual_operation_emits_only_cancelled(
    qapp: QApplication,
) -> None:
    cancelled: list[bool] = []
    results: list[object] = []

    def operation(context: OperationContext) -> str:
        context.cancel()
        return "ignored"

    task = OperationTask(operation, contextual=True)
    task.signals.cancelled.connect(lambda: cancelled.append(True))
    task.signals.succeeded.connect(results.append)

    task.run()
    qapp.processEvents()

    assert cancelled == [True]
    assert results == []
