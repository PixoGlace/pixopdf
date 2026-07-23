# Packaging

PyInstaller builds must run natively on each target OS; artifacts are not cross-platform. The workflow builds independently on Windows, macOS and Linux. The spec includes the branding assets and the complete GPLv3 license. Future releases should add OS code signing/notarization, reproducibility checks, native dependency notices and installer formats. PDFium and Qt assets must be audited in each bundle.
