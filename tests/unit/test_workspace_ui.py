from io import BytesIO
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QListWidget,
    QListWidgetItem,
)

from pixopdf.domain.document import SourceDocument
from pixopdf.domain.page import PageReference
from pixopdf.domain.project import PdfProject
from pixopdf.pdf.renderer import PdfRenderer
from pixopdf.ui.workspace.workspace_page import (
    A4_PORTRAIT,
    PAGE_ID_ROLE,
    PageListWidget,
    PdfDropZone,
    WorkspacePage,
)


class ImmediateRenderer(PdfRenderer):
    def render_page(self, file_path: Path, page_index: int, width: int, height: int) -> bytes:
        image = Image.new("RGB", (width, height), "white")
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


class UnexpectedRenderer(PdfRenderer):
    def __init__(self) -> None:
        self.calls = 0

    def render_page(self, file_path: Path, page_index: int, width: int, height: int) -> bytes:
        self.calls += 1
        raise AssertionError("A blank page must not be rendered with PDFium")


def project_with_pages(count: int = 3) -> PdfProject:
    project = PdfProject()
    project.add_document(SourceDocument.create(Path("sample.pdf"), count))
    return project


def project_with_blank_pages(count: int = 5) -> PdfProject:
    project = PdfProject()
    project.pages.extend(PageReference.blank() for _ in range(count))
    return project


def page_list_with_ids(*page_ids: str) -> PageListWidget:
    pages = PageListWidget()
    pages.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    for page_id in page_ids:
        item = QListWidgetItem(page_id)
        item.setData(PAGE_ID_ROLE, page_id)
        pages.addItem(item)
    return pages


def test_home_drop_zone_accepts_only_local_pdf_files(qapp: QApplication) -> None:
    zone = PdfDropZone()
    dropped: list[list[str]] = []
    zone.files_dropped.connect(dropped.append)
    pdf_path = "/tmp/rapport.pdf"
    pdf_mime = QMimeData()
    pdf_mime.setUrls([QUrl.fromLocalFile(pdf_path)])
    enter_event = QDragEnterEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        pdf_mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    zone.dragEnterEvent(enter_event)

    assert enter_event.isAccepted()
    assert zone.property("dragActive")

    drop_event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        pdf_mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    zone.dropEvent(drop_event)

    assert drop_event.isAccepted()
    assert dropped == [[pdf_path]]
    assert not zone.property("dragActive")

    invalid_mime = QMimeData()
    invalid_mime.setUrls([QUrl.fromLocalFile("/tmp/notes.txt")])
    invalid_event = QDragEnterEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        invalid_mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    zone.dragEnterEvent(invalid_event)
    assert not invalid_event.isAccepted()


def test_reordered_ids_moves_non_contiguous_selection_to_end(qapp: QApplication) -> None:
    pages = page_list_with_ids("a", "b", "c", "d", "e")
    pages.item(1).setSelected(True)
    pages.item(3).setSelected(True)

    assert pages._reordered_ids(5) == ["a", "c", "e", "b", "d"]


def test_reordered_ids_moves_item_backward_and_handles_drop_in_selection(
    qapp: QApplication,
) -> None:
    pages = page_list_with_ids("a", "b", "c", "d", "e")
    pages.item(3).setSelected(True)
    assert pages._reordered_ids(1) == ["a", "d", "b", "c", "e"]

    pages.clearSelection()
    pages.item(1).setSelected(True)
    pages.item(2).setSelected(True)
    assert pages._reordered_ids(2) == ["a", "b", "c", "d", "e"]


def test_workspace_states_search_and_actions(qapp: QApplication) -> None:
    workspace = WorkspacePage(ImmediateRenderer())
    project = project_with_pages()
    workspace.refresh(project)

    assert workspace._thread_pool.maxThreadCount() == 1
    assert workspace.page_stack.currentWidget() is workspace.pages
    assert workspace.export_button.isEnabled()
    assert not workspace.delete_button.isEnabled()

    workspace.pages.item(1).setSelected(True)
    qapp.processEvents()
    assert workspace.delete_button.isEnabled()

    rotations: list[tuple[list[int], int]] = []
    workspace.rotate_requested.connect(
        lambda indices, degrees: rotations.append((indices, degrees))
    )
    workspace.rotate_left_button.click()
    assert rotations == [([1], -90)]

    workspace.search.setText("page 2")
    assert sum(not workspace.pages.item(row).isHidden() for row in range(3)) == 1
    assert workspace.pages.selectedItems() == []
    assert workspace.pages.dragDropMode() == QListWidget.DragDropMode.NoDragDrop

    workspace.search.clear()
    assert workspace.pages.dragDropMode() == QListWidget.DragDropMode.InternalMove
    workspace._thread_pool.waitForDone()
    qapp.processEvents()


def test_empty_workspace_uses_thumbnail_area_empty_state(qapp: QApplication) -> None:
    workspace = WorkspacePage(ImmediateRenderer())
    workspace.refresh(PdfProject())

    assert workspace.page_stack.currentWidget() is workspace.empty_state
    assert not workspace.export_button.isEnabled()
    assert workspace.empty_title.text() == "Aucune page"
    assert "vignettes ici" in workspace.empty_detail.text()
    workspace.shutdown()


def test_options_blank_and_move_actions_emit_expected_values(qapp: QApplication) -> None:
    workspace = WorkspacePage(UnexpectedRenderer())
    project = project_with_blank_pages()
    workspace.refresh(project)
    page_ids = [str(page.id) for page in project.pages]
    blank_requests: list[tuple[int, float, float]] = []
    reordered: list[list[object]] = []
    workspace.blank_page_requested.connect(
        lambda index, width, height: blank_requests.append((index, width, height))
    )
    workspace.reorder_requested.connect(reordered.append)

    workspace.blank_page_button.click()
    assert blank_requests == [(5, *A4_PORTRAIT)]

    workspace.pages.item(1).setSelected(True)
    workspace.pages.item(3).setSelected(True)
    qapp.processEvents()
    workspace.blank_page_button.click()
    workspace.blank_before_action.trigger()
    assert blank_requests[-2:] == [(4, *A4_PORTRAIT), (1, *A4_PORTRAIT)]

    workspace.move_start_button.click()
    workspace.move_previous_button.click()
    workspace.move_next_button.click()
    workspace.move_end_button.click()

    assert reordered == [
        [page_ids[1], page_ids[3], page_ids[0], page_ids[2], page_ids[4]],
        [page_ids[1], page_ids[0], page_ids[3], page_ids[2], page_ids[4]],
        [page_ids[0], page_ids[2], page_ids[1], page_ids[4], page_ids[3]],
        [page_ids[0], page_ids[2], page_ids[4], page_ids[1], page_ids[3]],
    ]

    workspace.shutdown()


def test_move_button_limits_and_search_state(qapp: QApplication) -> None:
    workspace = WorkspacePage(UnexpectedRenderer())
    workspace.refresh(project_with_blank_pages(4))

    workspace.pages.item(0).setSelected(True)
    qapp.processEvents()
    assert not workspace.move_start_button.isEnabled()
    assert not workspace.move_previous_button.isEnabled()
    assert workspace.move_next_button.isEnabled()
    assert workspace.move_end_button.isEnabled()
    assert workspace.blank_before_action.isEnabled()
    assert workspace.blank_after_action.isEnabled()

    workspace.pages.clearSelection()
    workspace.pages.item(3).setSelected(True)
    qapp.processEvents()
    assert workspace.move_start_button.isEnabled()
    assert workspace.move_previous_button.isEnabled()
    assert not workspace.move_next_button.isEnabled()
    assert not workspace.move_end_button.isEnabled()

    workspace.search.setText("page blanche")
    assert workspace.pages.selectedItems() == []
    assert all(not button.isEnabled() for button in workspace._move_buttons.values())
    assert not workspace.blank_before_action.isEnabled()
    assert not workspace.blank_after_action.isEnabled()
    assert "Effacez la recherche" in workspace.move_hint.text()
    assert workspace.pages.dragDropMode() == QListWidget.DragDropMode.NoDragDrop

    workspace.shutdown()


def test_blank_page_thumbnail_is_local_non_null_and_cached(qapp: QApplication) -> None:
    renderer = UnexpectedRenderer()
    workspace = WorkspacePage(renderer)
    project = PdfProject()
    blank_page = PageReference.blank(420.0, 595.0).rotated(90)
    project.pages.append(blank_page)

    workspace.refresh(project)

    item = workspace.pages.item(0)
    assert renderer.calls == 0
    assert workspace._thumbnail_tasks == {}
    assert not item.icon().isNull()
    assert "420 × 595 points" in item.toolTip()
    assert "90°" in item.text()
    cache_key = ((420.0, 595.0), 90)
    assert cache_key in workspace._blank_thumbnails
    assert (
        workspace._blank_thumbnail(*cache_key).cacheKey()
        == workspace._blank_thumbnails[cache_key].cacheKey()
    )

    workspace.shutdown()
