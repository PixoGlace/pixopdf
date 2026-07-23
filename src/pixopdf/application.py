import sys

from PySide6.QtWidgets import QApplication

from pixopdf.pdf.pikepdf_backend import PikePdfBackend
from pixopdf.services.project_service import ProjectService
from pixopdf.ui.main_window import MainWindow


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PixoPDF")
    app.setOrganizationName("PixoGlace")
    window = MainWindow(ProjectService(PikePdfBackend()))
    window.show()
    return app.exec()
