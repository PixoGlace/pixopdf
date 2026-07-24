# Architecture

The UI calls application services and never edits a PDF itself. `PdfProject` owns
source metadata and an ordered list of immutable `PageReference` values. Commands
mutate only this virtual order and keep reversible state. The page grid stores the
page UUID, so drag-and-drop and subsequent actions always address the domain page
the user can see. Each reference also owns a monotonic display number, distinct
from its source index and current position, plus reversible visual change flags.
Moving, rotating, duplicating or inserting a page therefore never renumbers an
existing page. Deleting is also virtual: the page stays in the grid with a gray
marker and is omitted only from the export snapshot. Undo/redo and direct restore
recover both content state and visual markers.

`PdfBackend` isolates structural PDF operations; `PdfRenderer` isolates rendering.
Import, export and thumbnail generation run in `QThreadPool` tasks so the Qt event
loop remains responsive. Qt pixmaps are created only on the UI thread. PDFium has
process-wide mutable state and is not thread-safe, so every PDFium call is protected
by a global lock and the preview pool uses a single background worker. The in-memory
LRU cache is capped at 200 entries.

Export resolves references at the last moment, opens each source once, closes all
PDF handles, then atomically replaces the destination with a unique temporary file.
Every source document remains untouched.

Split planning converts each chosen strategy into zero-based groups over active
pages. Every group is exported to a temporary directory first; completed outputs
are moved into the selected destination only after every PDF has been generated.
Existing output files are never overwritten.
