# Roadmap

Each phase requires unit/integration tests, accessibility review, local-only processing, dependency/license review and native-platform validation.

- **0 — Foundation:** architecture, CI, logging, themes, home screen. Validate startup and layering; risk: native dependencies.
- **1 / 0.1.0 — Organizer:** imports, thumbnails, selection, reorder, rotate, delete, duplicate, merge, split by page/batch/ranges, blank pages, undo. Risk: large files; test encrypted/corrupt PDFs.
- **2 / 0.2.0 — Advanced layout:** extraction presets, A4/A5, 2/4-up and margins. Risk: geometry and print boxes.
- **3 / 0.3.0 — Annotation:** text, images, drawn/PNG visual signatures, dates, watermark, numbering. A visual signature is not a cryptographic digital signature.
- **4 / 0.4.0 — Conversion:** images↔PDF, embedded images, resolution and simple batches.
- **5 / 0.5.0 — Security:** passwords, permissions, authorized unlocking, metadata, pyHanko signatures, PAdES.
- **6 / 0.6.0 — Optimization:** images, resolution, resources, profiles, size estimates.
- **7 / 0.7.0 — OCR:** optional local Tesseract/OCRmyPDF, language/page/batch choices.
- **8 / 1.0.0 — Productivity:** presets, favorites, history, queues, recipes, optional CLI/plugins and i18n.

Cloud processing, telemetry and silent source modification are explicitly out of scope for every phase.
