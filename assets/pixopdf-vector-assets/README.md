# PixoPDF vector assets

This package contains original SVG assets for the PixoPDF desktop application.

## Main files

- `pixopdf-logo-light.svg`
- `pixopdf-logo-dark.svg`
- `pixopdf-app-icon-light.svg`
- `pixopdf-app-icon-dark.svg`
- `pixopdf-icons-light.svg`
- `pixopdf-icons-dark.svg`
- `pixopdf-icon-sprite.svg`

## Individual icons

Each icon is provided in both themes under:

- `icons/light/`
- `icons/dark/`

Available icons:

`home`, `recent`, `tools`, `settings`, `about`, `open`, `export`,
`merge`, `organize`, `split`, `layout`, `sign`, `convert`, `secure`,
`compress`.

## Qt / PySide6 use

The individual SVG files are intentionally built from basic paths, rectangles,
circles and lines. They avoid bitmap images, filters and external fonts inside
the icons, which makes them suitable for `QIcon`, `QSvgRenderer` and Qt resources.

Example:

```python
from PySide6.QtGui import QIcon

button.setIcon(QIcon(":/icons/light/merge.svg"))
```

Use the light icon set on light surfaces and the dark icon set on dark surfaces.
