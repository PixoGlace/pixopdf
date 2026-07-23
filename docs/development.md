# Development

Use Python 3.12+ and Poetry 2.x. Run `poetry install --with dev`; Poetry creates
and manages the virtual environment. Use `poetry env info` to inspect it and
`poetry env activate` only when an interactive shell is useful. `make run`,
`make test`, `make lint`, `make format`, `make typecheck`, and `make check`
execute tools through `poetry run`. Python follows Ruff formatting, strict mypy
typing, pathlib paths and domain/service/UI separation. Branding resources in
`assets/` are resolved through `pixopdf.assets`, included in Poetry archives and
copied into PyInstaller bundles.
