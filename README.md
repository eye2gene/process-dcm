# Process DCM

[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg?style=plastic)](https://github.com/eye2Gene/process-dcm/graphs/commit-activity)
[![GitHub](https://img.shields.io/github/license/eye2Gene/process-dcm?style=plastic)](https://github.com/eye2Gene/process-dcm)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/eye2Gene/process-dcm?display_name=tag&logo=github&style=plastic)](https://github.com/eye2Gene/process-dcm/releases)
[![GitHub Release](https://img.shields.io/github/release-date/eye2Gene/process-dcm?style=plastic&logo=github)](https://github.com/eye2Gene/process-dcm/releases)
[![PyPI](https://img.shields.io/pypi/v/process-dcm?style=plastic&logo=pypi)](https://pypi.org/project/process-dcm/)
[![Python](https://img.shields.io/pypi/pyversions/process-dcm?style=plastic&logo=python)](https://pypi.org/project/process-dcm/)
[![uv](https://img.shields.io/endpoint?style=plastic&url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?style=plastic&url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?style=plastic&url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)

## About The Project

Python library and app to extract images from DCM files with metadata in a JSON-based standard format.

It targets ophthalmic DICOMs (OCT, fundus photography, fluorescein angiography, SLO, Optomap, ...), writes one folder
per acquisition with the extracted frames as PNG/JPG/WEBP plus a `metadata.json`, and can anonymise patient
identifiers while keeping a `study_id -> patient_id` mapping.

## Installation and Usage

```bash
pip install process-dcm
# or, without touching your environment
uvx process-dcm --help
```

```bash
 Usage: process-dcm [OPTIONS] {input_path}

 Process DICOM files in subfolders, extract images and metadata.

╭─ Arguments ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    input_path      <path>  Input path to either a DCM file or a folder containing DICOM files. [required]               │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --image_format        -f      <str>    Image format for extracted images (png, jpg, webp). [default: png]                 │
│ --output_dir          -o      <path>   Output directory for extracted images and metadata. [default: exported_data]       │
│ --group               -g               Re-group DICOM files in a given folder by AcquisitionDateTime.                     │
│ --tol                 -t      <float>  Tolerance in seconds for grouping DICOM files by AcquisitionDateTime. Only used    │
│                                        when --group is set.                                                               │
│ --n_jobs              -j      <int>    Number of parallel jobs. [default: 1]                                              │
│ --mapping             -m      <str>    Path to CSV containing patient_id to study_id mapping. If not provided and         │
│                                        patient_id is anonymised, a 'study_2_patient.csv' file will be generated.          │
│ --keep                -k      <str>    Keep the specified fields (p: patient_key, n: names, d: date_of_birth, D:          │
│                                        year-only DOB, g: gender)                                                          │
│ --preserve_folder_structure  -p        Mirror the input folder structure under the output directory instead of the flat   │
│                                        '{patient}_{date}_{hash}_{eye}_{modality}.DCM' folders. Not compatible with        │
│                                        --group or --reset.                                                                │
│ --keep_dcm_name_as_folder / --no_keep_dcm_name_as_folder                                                                  │
│                                        With --preserve_folder_structure, write each DICOM's images into a folder named    │
│                                        after the file. Disable to write all acquisitions of an input folder into one      │
│                                        output folder. [default: keep_dcm_name_as_folder]                                  │
│ --relative_source_file                 Write metadata 'source_file' relative to INPUT_PATH instead of the current working │
│                                        directory.                                                                         │
│ --overwrite           -w               Overwrite existing images if found.                                                │
│ --reset               -r               Reset the output directory if it exists.                                           │
│ --quiet               -q               Silence verbosity.                                                                  │
│ --version             -V               Prints app version.                                                                │
│ --install-completion                   Install completion for the current shell.                                          │
│ --show-completion                      Show completion for the current shell, to copy it or customize the installation.   │
│ --help                -h               Show this message and exit.                                                        │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### Output layout

By default every acquisition group (DICOMs sharing a `FrameOfReferenceUID`, or an acquisition time with `--group`)
is written to one flat, self-describing folder under the output directory:

```txt
exported_data/
└── {PatientKey}_{Date}_{Time}_{Hash}_{Laterality}_{Modality}.DCM/
    ├── {Modality}-{GroupID}_{FrameIndex}.{png|jpg|webp}
    └── metadata.json
```

`--preserve_folder_structure` (`-p`) mirrors the input tree instead. The group is written under the relative folder of
its first DICOM, in a leaf folder named after that file (drop the leaf with `--no_keep_dcm_name_as_folder`):

```txt
exported_data/
└── {relative input folder}/{dicom file stem}/
    ├── {Modality}-{GroupID}_{FrameIndex}.{png|jpg|webp}
    └── metadata.json
```

This layout cannot be combined with `--group` or `--reset`. In both layouts each image entry in `metadata.json` records
its `source_file` relative to the current working directory; `--relative_source_file` makes it relative to `INPUT_PATH`
instead. The metadata format is versioned by `parser_version` (currently 1.7.0). Each image entry carries its own
`laterality` and `scan_datetime`, because a DICOM group may hold scans of both eyes taken at different times; the
series-level `laterality` is `B` and the exam-level `scan_datetime` is the earliest one in that case.

## Project structure

```txt
process-dcm/
├── .github/
│   └── workflows/
│       ├── ci.yml              # Calls reusable CI from e2g-workflows
│       └── release.yml         # Semantic release + publish on main
├── .kiro/
│   └── steering/
│       ├── commits.md          # Conventional commit rules for Kiro
│       ├── python.md           # Python coding standards for Kiro
│       └── safety.md           # Command safety guardrails for Kiro
├── .vscode/
│   ├── extensions.json         # Recommended VS Code/Kiro extensions
│   └── settings.json           # Editor settings (Ruff, pytest, etc.)
├── src/
│   └── process_dcm/
│       ├── __init__.py         # Package version via importlib.metadata
│       ├── __main__.py         # python -m support
│       ├── main.py             # Typer CLI entry point (`process-dcm`)
│       ├── const.py            # ImageModality / ModalityFlag enums
│       ├── py.typed            # PEP 561 typing marker
│       └── utils.py            # DICOM processing, grouping, metadata
├── tests/
│   ├── conftest.py             # Shared pytest fixtures and warning filters
│   ├── test_*.py
│   └── <sample DICOMs>         # Small fixtures committed to git
├── .cruft.json                 # Links project to e2g-pypkg template
├── .editorconfig               # Editor-agnostic formatting rules
├── .gitignore
├── .python-version             # Pin Python version for uv
├── CLAUDE.md                   # AI rules for Claude CLI/VS Code
├── README.md
├── justfile                    # Command runner (just qa, just test, etc.)
└── pyproject.toml              # Project metadata, deps, tool config
```

**Key files:**

- **`.github/workflows/`** — CI calls the shared [e2g-workflows](https://github.com/eye2Gene/e2g-workflows) reusable workflow. CI logic is centralised there.
- **`.kiro/steering/`** — AI steering rules loaded automatically by Kiro. Enforces team coding standards.
- **`CLAUDE.md`** — Same AI rules for Claude CLI/VS Code users, plus project-specific notes.
- **`.vscode/`** — Shared editor settings (Ruff format-on-save, pytest discovery, recommended extensions). Works in VS Code and Kiro out of the box.
- **`justfile`** — Single interface for all dev commands. CI uses the same recipes, so local and CI behaviour match.
- **`.cruft.json`** — Template tracking. Run `cruft update` to pull improvements from [e2g-pypkg](https://github.com/eye2Gene/e2g-pypkg).

## Development

Requirements: [uv](https://docs.astral.sh/uv/getting-started/installation/). `just` is installed into the
environment by `uv sync` (`rust-just`), so `uv run just ...` always works; a system-wide `just` is optional.

```bash
# Clone the repo
git clone git@github.com:eye2Gene/process-dcm.git
cd process-dcm

# Create the virtual environment (uses .python-version -> 3.12)
uv venv

# Activate the virtual environment
source .venv/bin/activate

# Install the project (editable) and all dev dependency groups
uv sync
```

Python 3.11 is the minimum supported version; development and CI default to 3.12, and CI also tests 3.11 and 3.13.

Run tests (parallel, with coverage):

```bash
just test             # or: uv run pytest
just test -k optomap  # pass any pytest args through
just pdb              # single process, drop into the debugger on failure
```

Run quality checks (format, lint, type check with ty, dependency audit, then tests):

```bash
just qa       # fixes what it can
just ci       # check only, what CI runs
just qa-all   # qa + tests
```

### Test data

Most fixtures are small DICOMs committed under `tests/`. The larger sample set `tests/example_dir` (about 625 MB) is
**not** in git (see `.gitignore`); the tests that depend on it are skipped automatically when the folder is absent, both
locally and in CI. If you need them, ask the maintainers for a copy and unpack it at `tests/example_dir/`.

Maintainers may also keep a `tests_local/` folder, ignored by git, with smoke tests that run process-dcm on
vendor-conversion outputs: Topcon FDA and Heidelberg E2E files exported to DICOM with
[OCT-Converter](https://github.com/marksgraham/OCT-Converter), plus a Heidelberg DICOMDIR export. That data cannot
be shared, so the folder exists only on maintainers' machines and is not part of `just test`; run it explicitly with
`uv run pytest tests_local`. Its own README explains where the data comes from and how to regenerate it.

Several tests compare MD5 hashes of generated PNGs. PNG bytes depend on the Pillow encoder version even when the pixels
are identical, so the expected hash lists accept one value per known encoder. If a dependency bump changes a hash,
verify the pixels are unchanged before adding the new value.

## How releases work

This project uses [conventional commits](https://www.conventionalcommits.org/) and [python-semantic-release](https://python-semantic-release.readthedocs.io/):

1. Develop on a feature branch with conventional commit messages (`feat:`, `fix:`, `docs:`, etc.)
2. Open a PR and merge to `main` when tests pass
3. On merge, GitHub Actions automatically:
   - Determines the next version from commit messages
   - Updates the changelog
   - Creates a git tag and GitHub Release
   - Builds and publishes the package

Never edit the version number by hand: it lives only in `pyproject.toml` and is read at runtime via
`importlib.metadata` (`process_dcm.__version__`). `CHANGELOG.md` is regenerated at every release, so don't edit it
either; the changelog kept by commitizen up to v0.10.0 is preserved in [CHANGELOG-pre-1.0.0.md](CHANGELOG-pre-1.0.0.md).

## Publishing to PyPI

This project publishes to [PyPI.org](https://pypi.org/project/process-dcm/) using [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC). No tokens needed — the repo is configured as a trusted publisher on PyPI (owner `eye2Gene`, repository `process-dcm`, workflow `release.yml`).

## AI-assisted development

This project includes configuration for AI coding assistants:

- **Kiro**: `.kiro/steering/` contains rules for Python style, commit messages, and command safety
- **Claude**: `CLAUDE.md` contains the same rules in Claude's format

These are committed to git so all contributors get consistent AI behaviour. No personal setup required — just open the project in Kiro or Claude and the rules apply automatically.

## Keeping up with template updates

This project follows the [e2g-pypkg](https://github.com/eye2Gene/e2g-pypkg) template and uses [cruft](https://cruft.github.io/cruft/) to stay in sync with template improvements.

Check if there are template updates available:

```bash
uv run cruft check
```

See what would change:

```bash
uv run cruft diff
```

Apply template updates to your project:

```bash
uv run cruft update
```

If there are merge conflicts, cruft will create `.rej` files showing the rejected changes. Resolve them manually, then commit.

> **Tip:** Run `cruft update` on a clean branch so you can review the changes in a PR.

## Author

Process DCM was created in 2024 by Alan Wilter at the Moorfields Ophthalmic Reading Centre & Clinical AI Lab and is
maintained by [Eye2Gene](https://github.com/eye2Gene). Licensed under the [MIT License](LICENSE).

Aligned with the [eye2Gene/e2g-pypkg](https://github.com/eye2Gene/e2g-pypkg) project template.
