import os
import tempfile
from pathlib import Path

import pikepdf

from pixopdf.domain.project import PdfProject

from .backend import PdfBackend
from .exceptions import PdfExportError, PdfOpenError, PdfPasswordRequiredError


class PikePdfBackend(PdfBackend):
    def page_count(self, path: Path) -> int:
        if not path.is_file():
            raise PdfOpenError(f"Fichier introuvable : {path.name}")
        try:
            with pikepdf.open(path) as pdf:
                return len(pdf.pages)
        except pikepdf.PasswordError as exc:
            raise PdfPasswordRequiredError(f"{path.name} est protégé par un mot de passe.") from exc
        except pikepdf.PdfError as exc:
            raise PdfOpenError(f"{path.name} n’est pas un PDF valide ou est endommagé.") from exc
        except OSError as exc:
            raise PdfOpenError(f"Impossible de lire {path.name}.") from exc

    def export(self, project: PdfProject, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.stem}-",
            suffix=".tmp",
            dir=destination.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            output = pikepdf.Pdf.new()
            opened: dict[Path, pikepdf.Pdf] = {}
            try:
                for page in project.pages:
                    if page.is_blank:
                        output.add_blank_page(page_size=page.blank_size or (595.28, 841.89))
                    else:
                        source = project.source_for(page)
                        if source.path not in opened:
                            opened[source.path] = pikepdf.open(source.path)
                        pdf = opened[source.path]
                        if page.source_page_index is None:
                            raise PdfExportError("Référence de page source invalide")
                        output.pages.append(pdf.pages[page.source_page_index])
                    if page.rotation:
                        output.pages[-1].rotate(page.rotation, relative=True)
                output.save(temporary)
            finally:
                output.close()
                for pdf in opened.values():
                    pdf.close()
            os.replace(temporary, destination)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise PdfExportError("L’export du PDF a échoué") from exc
