# Contributing to Naadrik

## Workflow

* Branch from `main` as `feature/<topic>` or `fix/<topic>`; merge back with `--no-ff` once tests pass.
* Commit small, logical units with [Conventional Commits](https://www.conventionalcommits.org/):
  `feat(sound): ...`, `fix(depth): ...`, `docs: ...`, `test: ...`, `build: ...`, `chore: ...`.
* Each milestone is tagged (`v0.1.0`, ...) and recorded in `CHANGELOG.md`.

## Before pushing

```bash
pip install -e ".[dev]"
ruff check .
black --check .
pytest
```

CI runs the same commands on every push.

## Code style

* Python 3.11+, type hints throughout, `black` and `ruff` (config in `pyproject.toml`).
* Small, focused functions with meaningful names. Comments explain *why*, not *what*.
* Every tunable number that affects what the user hears belongs in `config.yaml`, not in code.
* Raise a `NaadrikError` subclass with an actionable message for anything a user can fix
  (missing camera, model or audio device). Never fail silently.
* Keep the audio callback free of allocation-heavy work, locks held for long, I/O and logging.

## Tests

Mappings are the product: any change to position, distance, colour or priority mapping needs a
test. Audio tests should assert measurable properties (pitch, pulse count, channel balance)
rather than exact sample values, so timbre tuning does not break them.

## Design decisions

Record any non-obvious choice in `docs/decisions.md` with the date, the options considered and
the reason.
