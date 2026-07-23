# ADR 0001 — PDF backends

Status: accepted. pikepdf performs structural editing and export; pypdfium2 renders previews. Both sit behind interfaces so workers and tests can substitute implementations. pyHanko may later provide digital signatures. PyMuPDF is deliberately absent as the primary backend because its AGPL/commercial licensing needs a separate explicit decision. Dependency notices remain mandatory under PixoPDF's GPL-3.0-only distribution.

PDFium must never be called concurrently inside one process. Thumbnail rendering
therefore stays asynchronous relative to the UI but is serialized behind a global
lock. This prevents corruption of PDFium's shared font, color-space and parser state.
