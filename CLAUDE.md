# Python coding standards

When generating Python code (modules, classes, functions):

- Include Google-style docstrings.
- Follow Ruff defaults, enforcing rule D212 and line-length limits.
- Use modern type annotations (Python >=3.12).
- Do not use `from typing import ...`.
- Use 4 spaces for indentation.
- Output code only, no explanations.

When generating tests:

- Use pytest.
- Assume pytest is already installed (no setup instructions).
- Include complete and sophisticated unit tests with proper setup/teardown if needed.
- Cover important edge cases.
- Add Python 3.12 type annotations for all functions (no `from typing import`).
- Always specify return types.
- Each test function must include a one-line docstring describing its purpose.
- Output code only, no explanations.

# Git commit message standards

When generating Git commit messages:

- Generate commit messages only from the output of `git diff --cached`.
- Treat the staged diff as the single source of truth.
- If the staged diff is missing, empty, truncated, or ambiguous, ask for the complete output of `git diff --cached` instead of guessing.
- Use the Conventional Commits specification.
- Output only the commit subject (one line, no body, no explanations).
- Keep it concise (preferably <=72 characters).
- Use the imperative mood (e.g. "add", "fix", "remove").
- Choose the most appropriate type (`feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `build`, `ci`, `chore`, `style`, `revert`).
- Prefer the most specific valid Conventional Commit type. Do not use `chore` when another type (`refactor`, `test`, `docs`, `build`, `ci`, etc.) more accurately describes the staged changes.
- Select the commit type based on semantic intent, not file type. For example, updating dependencies without changing behaviour is typically `chore(deps): ...`, not `feat` or `fix`.
- Add a scope only when it meaningfully improves clarity.
- Append `!` only for breaking changes.
- Do not end the subject with a period.

# Command safety

## AWS CLI

Never execute `aws` commands automatically. Always present them to the user and ask them to run manually. This applies to any command that starts with `aws` or invokes the AWS CLI in any form.

## Destructive rm commands

Never automatically run `rm -rf` or `rm -r` on broad or sensitive paths. This includes:

- Home directory (`~/`, `$HOME`)
- Root or top-level system paths (`/`, `/usr`, `/etc`, `/var`, `/opt`, `/mnt`)
- Any path that could contain large amounts of user data (e.g., `~/Documents`, `~/Projects`, `/mnt/data*`)
- Any recursive delete where the target is a variable or glob that could expand unexpectedly

For these cases, present the command and ask the user to run it manually.

Deleting small, specific files or build artifacts (e.g., `rm -rf node_modules`, `rm -rf .venv`, `rm -rf dist/`) within a project directory is fine.

# Project: Process DCM

Python library and CLI (`process-dcm`) that extracts images from ophthalmic DICOM files (OCT, fundus, FA, SLO,
Optomap, ...) into PNG/JPG/WEBP plus one `metadata.json` per acquisition, with optional patient anonymisation.

## Layout and tooling

This repo follows the Eye2Gene [e2g-pypkg](https://github.com/eye2Gene/e2g-pypkg) template (tracked via `.cruft.json`):

- src layout: `src/process_dcm/` with `main.py` (Typer CLI, entry point `process-dcm`), `utils.py` (processing),
  `const.py` (`ImageModality` / `ModalityFlag`). Tests and sample DICOMs live in `tests/`.
- uv for environments and locking, `uv_build` as build backend. No Poetry.
- Ruff for formatting and linting (line length 120, `target-version = "py311"`), ty for type checking. No mypy, no pre-commit.
- pytest with coverage, `-n auto` (pytest-xdist) by default. Warnings are errors (see `tests/conftest.py`).
- `just` recipes are the single interface for dev commands; CI runs the same recipes.
- Minimum Python 3.11 (ruff targets it). Develop with 3.12 (`.python-version`). Move both to 3.12 once every
  Eye2Gene consumer of process-dcm is on 3.12.

## Commands

```bash
uv sync                      # create .venv with all dev groups
just qa                      # ruff format + ruff check --fix + ty check + uv audit
just ci                      # same, without fixes (what CI runs)
just test [PYTEST_ARGS]      # pytest with coverage, parallel
just pdb [PYTEST_ARGS]       # pytest --pdb, single process
just build                   # uv build -> dist/
uv run process-dcm INPUT -o OUT -f png --overwrite   # run the CLI
```

## Testing notes

- `tests/example_dir` (~625 MB of sample DICOMs) is deliberately not in git. Tests that need it skip when it is absent.
- Many tests assert MD5 hashes of generated PNGs and of `metadata.json` (minus its last lines). PNG bytes depend on the
  Pillow version even when pixels are identical, so hash lists accept several values. When a dependency bump changes a
  hash, verify pixels are unchanged before appending the new hash.
- `metadata.json` carries `parser_version` ([1, 5, 3]) for the JSON format and `py_dcm_version` for the package
  version. Bump `parser_version` whenever the metadata schema changes.

## Releases

- Conventional commits only. Merging to `main` runs `release.yml`: python-semantic-release computes the version from
  commit messages, updates `pyproject.toml` and `CHANGELOG.md`, tags, creates the GitHub Release, and publishes to
  PyPI via trusted publishing. Never edit the version by hand.
- The package version is read at runtime from installed metadata (`process_dcm.__version__`); there is no hardcoded
  version string in the source.
