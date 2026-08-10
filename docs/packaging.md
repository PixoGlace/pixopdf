# Packaging

PyInstaller builds run natively on each target OS; artifacts are not
cross-platform. The reusable build workflow produces two user-facing choices per
platform:

| Platform | Portable | Installer |
| --- | --- | --- |
| macOS arm64 | `PixoPDF-macos-arm64-portable.zip` | `PixoPDF-macos-arm64.dmg` |
| macOS Intel | `PixoPDF-macos-x86_64-portable.zip` | `PixoPDF-macos-x86_64.dmg` |
| Windows x64 | `PixoPDF-windows-x86_64-portable.zip` | `PixoPDF-windows-x86_64-setup.exe` |
| Linux x86_64 | `PixoPDF-linux-x86_64-portable.tar.gz` | `pixopdf_<version>_amd64.deb` |

`packaging/create_packaging_art.py` deterministically derives the application
icons, DMG background, Windows wizard art and Linux banner from the checked-in
PixoPDF identity. Inno Setup builds a per-user Windows installer with an optional
desktop shortcut. The Debian package installs the executable
under `/opt/PixoPDF`, a launcher under `/usr/bin`, a desktop entry, icon and
AppStream metadata. The DMG presents the `.app` beside an Applications shortcut.

The spec includes branding assets and the complete GPLv3 license. Release
publication verifies every expected asset and generates SHA-256 checksums. CI uses
ad-hoc macOS signing so the bundle structure can be verified, but production code
signing, Apple notarization, Windows Authenticode, reproducibility checks and a
complete native dependency-notice audit still require release credentials.

Local commands:

```bash
make build            # application for the current OS
make package          # portable + installer for the current OS
make release-current  # checks + build + both distribution formats
```
