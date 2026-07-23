class PdfError(Exception):
    pass


class PdfOpenError(PdfError):
    pass


class PdfPasswordRequiredError(PdfError):
    pass


class PdfInvalidPasswordError(PdfError):
    pass


class PdfExportError(PdfError):
    pass


class PdfRenderError(PdfError):
    pass


class UnsupportedPdfError(PdfError):
    pass
