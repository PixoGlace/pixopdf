# PixoPDF

**Organize, transform and protect your PDFs locally.**

**Organisez, transformez et protégez vos PDF localement.**

PixoPDF is a free, cross-platform PDF toolbox by [PixoGlace](https://github.com/PixoGlace), inspired by PixoCrop's sober visual language. It runs offline: **PixoPDF processes documents locally. Your files are not uploaded to a remote service.**

## Current MVP

- Open one or more PDFs and build a virtual page project
- Select, rotate, duplicate, delete and reorder pages without touching source files
- Keep page numbers stable while teal/amber badges identify moved or modified pages
- Insert A4/A5 blank pages, including landscape pages, anywhere in the project
- Undo and redo edits
- Search pages and resize previews
- Generate thumbnails, import and export without freezing the interface
- Merge and atomically export to a new PDF
- Light and dark PixoGlace themes
- Drop PDF files directly from the file manager

Splitting, advanced layout, annotations, conversion, security, compression, OCR and batch processing are on the roadmap. Unavailable tools are explicitly marked “Bientôt”.

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
executable with `make build`. Windows, macOS and Linux builds are produced
separately.

Contributions are welcome; see `CONTRIBUTING.md`. PixoPDF is independent from PixoCrop and does not introduce a runtime coupling with it.

## License

Copyright © 2026 PixoGlace. PixoPDF is licensed under the **GNU General Public License v3.0 only** (`GPL-3.0-only`), not MIT. See `LICENSE`. Dependencies retain their respective licenses; notably Qt/PySide6 (LGPL/GPL/commercial), pikepdf (MPL-2.0), pypdfium2 (Apache-2.0/BSD-3-Clause and PDFium notices), and Pillow (HPND). Optional pyHanko, OCRmyPDF and Tesseract components retain their own licenses.
