# PixoPDF

**Organize, transform and protect your PDFs locally.**

**Organisez, transformez et protégez vos PDF localement.**

PixoPDF is a free, cross-platform PDF toolbox by [PixoGlace](https://github.com/PixoGlace), inspired by PixoCrop's sober visual language. It runs offline: **PixoPDF processes documents locally. Your files are not uploaded to a remote service.**

## Current MVP

- Open one or more PDFs and build a virtual page project
- Select, rotate, duplicate, reorder and mark pages as deleted without touching source files
- Keep deleted pages visible in gray and restore them directly before export
- Keep page numbers stable while teal/amber badges identify moved or modified pages
- Insert A4/A5 blank pages, including landscape pages, anywhere in the project
- Undo and redo edits
- Search pages and resize previews
- Generate thumbnails, import and export without freezing the interface
- Merge and atomically export to a new PDF
- Split active pages into one PDF per page, fixed-size batches or custom ranges,
  with a live color-and-number preview on every thumbnail
- Review, remove or clear imported documents from the workspace without deleting
  the original files
- Use a three-panel workspace with opened files on the left, page thumbnails in
  the center and operation-specific options on the right
- Return to a clean Home drop zone that closes the current workspace and starts
  a fresh history
- Light and dark PixoGlace themes
- Switch instantly between French, English, Chinese and Arabic; the selected
  language is remembered and Arabic uses a right-to-left interface
- Use native Fichier, Édition, Affichage, Outils and Aide menus with persistent
  settings, an offline quick guide and project information
- Check GitHub releases without blocking PDF work and disable automatic checks
  from Settings when desired
- Access the PixoGlace Ko-fi sponsorship link from the permanent status bar
- Drop PDF files directly from the file manager

Advanced layout, annotations, conversion, security, compression, OCR and batch processing are on the roadmap. Unavailable tools are explicitly marked “Bientôt”.

Automatic update checks contact only the public GitHub releases API. No PDF,
file path or document metadata is included in that request.

## Development

Requires Python 3.12+, [Poetry](https://python-poetry.org/) 2.x and the native
requirements used by pikepdf/PySide6. Poetry creates and manages the virtual
environment; no manual activation is required.

```bash
poetry install --with dev
poetry run pixopdf
# or: make install && make run
```

Run all checks with `make check`. Build the Python package and a platform-native
application with `make build`. Windows and Linux receive an executable; macOS
receives a signed-ready `PixoPDF.app` bundle with the correct application menu.
The builds are produced separately.

Application preferences are available with `Ctrl+,` on every platform
(`⌘,` on macOS). They appear under **PixoPDF > Settings…** on macOS and
**Tools > Settings…** on Windows and Linux. Language and theme controls are
centralized in this dialog instead of occupying the workspace toolbar.

Contributions are welcome; see `CONTRIBUTING.md`. PixoPDF is independent from PixoCrop and does not introduce a runtime coupling with it.

## Showcase website

The multilingual PixoPDF showcase lives in `docs/`. It supports French,
English, Chinese and Arabic, light and dark themes, and the PixoGlace Ko-fi
sponsorship link. A single semantic HTML page contains the complete French
fallback; a small vanilla JavaScript layer switches the translation dictionary,
persists the theme, animates the presentation and resolves direct download
assets from the latest GitHub release. There is no JavaScript framework,
package manager or build step.

```bash
make docs-dev           # serve docs/ at http://localhost:8000
make docs-check         # validate i18n parity, links, assets and release wiring
poetry run python scripts/capture_docs_assets.py  # refresh app screenshots
```

Pushes to `main` that change `docs/` deploy the static export through the
GitHub Pages workflow directly, without a compilation step. The repository
Pages source must be set to
**GitHub Actions**. Once enabled, the public URL is
<https://pixoglace.github.io/pixopdf/>.

## License

Copyright © 2026 PixoGlace. PixoPDF is licensed under the **GNU General Public License v3.0 only** (`GPL-3.0-only`), not MIT. See `LICENSE`. Dependencies retain their respective licenses; notably Qt/PySide6 (LGPL/GPL/commercial), pikepdf (MPL-2.0), pypdfium2 (Apache-2.0/BSD-3-Clause and PDFium notices), and Pillow (HPND). Optional pyHanko, OCRmyPDF and Tesseract components retain their own licenses.
