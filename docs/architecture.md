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

Advanced file-producing operations follow the same rule. `LayoutService`,
`ConversionService`, `ProtectionService`, `SignatureService` and
`CompressionService` consume an immutable materialized project snapshot and
publish through sibling temporary files or staged directories. A digital
signature is always the final byte-level operation. Target-size compression
tests bounded vector-preserving candidates first, retains only the smallest
temporary candidate, and only allows the disclosed page-raster fallback after
explicit opt-in. Compression reports stage and page-level progress and checks a
cooperative cancellation token throughout expensive loops and immediately before
the atomic destination replacement.

The compression panel keeps its immediate indicative estimate while the user is
editing settings, then starts a debounced exact precompression in a dedicated
single-worker pool. Exact outputs are stored in a four-entry disk-backed LRU cache
keyed by source identity, active page state and immutable compression options.
Selecting the same settings updates the UI immediately, and exporting can publish
the cached artifact atomically instead of compressing it again. Stale, cancelled
and evicted previews are removed automatically, and the complete preview directory
is deleted when the application closes.

Split planning converts each chosen strategy into zero-based groups over active
pages. Every group is exported to a temporary directory first; completed outputs
are moved into the selected destination only after every PDF has been generated.
Existing output files are never overwritten. The UI maps these active-page groups
back to the complete thumbnail list, skipping soft-deleted pages, and stores all
output memberships on each item so overlapping custom ranges remain visible.
Colored borders are paired with numbered PDF badges and text tooltips.

Removing one source or clearing the complete workspace is implemented as an
undoable command. These commands only mutate the virtual project; original files
are never deleted.

The desktop shell uses one persistent three-column editor: source files on the
left, page thumbnails in the center and the active workflow options on the right.
Home is a separate central drop-zone state that hides both side panels. Returning
Home creates a new `PdfProject` and `CommandStack`; importing into any empty Home
state also resets stale history, preventing undo commands from a closed workspace
from modifying a newly opened project.
