from collections.abc import Callable

from pixopdf import application
from pixopdf.config import APP_NAME, ORGANIZATION, VERSION


def test_run_sets_cross_platform_application_identity_before_building_window(
    monkeypatch,
) -> None:
    events: list[tuple[object, ...]] = []
    backend = object()
    service = object()

    class FakeApplication:
        def __init__(self, arguments: list[str]) -> None:
            events.append(("application", arguments))

        def setApplicationName(self, value: str) -> None:
            events.append(("name", value))

        def setApplicationDisplayName(self, value: str) -> None:
            events.append(("display_name", value))

        def setApplicationVersion(self, value: str) -> None:
            events.append(("version", value))

        def setOrganizationName(self, value: str) -> None:
            events.append(("organization", value))

        def exec(self) -> int:
            events.append(("exec",))
            return 17

    class FakeWindow:
        def __init__(self, received_service: object) -> None:
            assert received_service is service
            events.append(("window",))

        def show(self) -> None:
            events.append(("show",))

        def check_for_updates_on_startup(self) -> None:
            raise AssertionError("The timer callback must not run synchronously")

    class FakeTimer:
        @staticmethod
        def singleShot(delay: int, callback: Callable[[], None]) -> None:
            events.append(("timer", delay, callback.__name__))

    def create_backend() -> object:
        events.append(("backend",))
        return backend

    def create_service(received_backend: object) -> object:
        assert received_backend is backend
        events.append(("service",))
        return service

    monkeypatch.setattr(application, "QApplication", FakeApplication)
    monkeypatch.setattr(application, "MainWindow", FakeWindow)
    monkeypatch.setattr(application, "QTimer", FakeTimer)
    monkeypatch.setattr(application, "PikePdfBackend", create_backend)
    monkeypatch.setattr(application, "ProjectService", create_service)
    monkeypatch.setattr(application.sys, "argv", ["pixopdf"])

    assert application.run() == 17
    assert events[:5] == [
        ("application", ["pixopdf"]),
        ("name", APP_NAME),
        ("display_name", APP_NAME),
        ("version", VERSION),
        ("organization", ORGANIZATION),
    ]
    assert events[5:] == [
        ("backend",),
        ("service",),
        ("window",),
        ("show",),
        ("timer", 1200, "check_for_updates_on_startup"),
        ("exec",),
    ]
