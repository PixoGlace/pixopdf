# Roadmap

Each phase requires unit/integration tests, accessibility review, local-only processing, dependency/license review and native-platform validation.

- **0 — Foundation:** architecture, CI, logging, themes, home screen. Validate startup and layering; risk: native dependencies.
- **1 / 0.1.0 — Organizer:** imports, thumbnails, selection, reorder, rotate, delete, duplicate, merge, split by page/batch/ranges, blank pages, undo. Risk: large files; test encrypted/corrupt PDFs.
- **Delivered — Advanced layout:** A3/A4/A5/Letter, portrait/landscape,
  margins and 2/4/6/9-up sheets.
- **Delivered in part — Annotation:** PNG/JPEG visual signatures and date
  stamps. Text, watermark and numbering remain planned. A visual signature is
  not a cryptographic digital signature.
- **Delivered — Conversion:** PDF→PNG/JPEG, images→PDF and embedded-image extraction.
- **Delivered — Security:** AES passwords, permissions, authorized unlocking
  and pyHanko PKCS#12 signatures.
- **Delivered — Optimization:** light/balanced/maximum profiles plus an advanced
  DPI and/or automatically tuned target-size mode, with a live estimate and an
  explicit quality floor.
- **7 / 0.7.0 — OCR:** optional local Tesseract/OCRmyPDF, language/page/batch choices.
- **8 / 1.0.0 — Productivity:** presets, favorites, history, queues, recipes, optional CLI/plugins and i18n.

Cloud processing, telemetry and silent source modification are explicitly out of scope for every phase.
