---
inclusion: auto
---

# Supply-chain safety

When adding a dependency, a tool, or anything a build fetches (Dockerfile, CI workflow, justfile, setup script):

- Python packages come from PyPI through `uv` and the lock file. `uv lock --exclude-newer "7 days"` keeps a release out until it is 7 days old; never bypass the lock (no `pip install` of unpinned packages, no package URLs).
- The one exception to the 7 days is a security fix that `uv audit` asks for. Do not write `exclude-newer-package` into `pyproject.toml` for it: run `just allow <package>` in the project. That opens a pull request listing the fix in `quarantine-exceptions.toml` of `eye2Gene/e2g-workflows` (merged by a reviewer, or by auto-merge once the repository enables it); after the merge, `just up` puts the list's active entries in the user-level uv configuration (`~/.config/uv/uv.toml`) before locking, so every Eye2Gene project takes the same fix with `just up`. CI refuses a `uv.lock` that lets a package in early without such an entry. An entry expires 7 days after the fix was uploaded; the next `just up` drops the pin.
- Prefer a Python package already in the lock to a tool from another ecosystem. Do not add node, npm or a JavaScript tool when a Python package does the job (e.g. Pillow writes WebP; sharp is not needed).
- Never fetch a prebuilt binary from a personal or third-party website, from a Docker image under a personal account, or from a GitHub project that repackages someone else's software. Build the tool from its upstream source: the release tarball from the project's own site, verified against the project's release signing key (committed in the repo, with its fingerprint pinned in the Dockerfile) and a pinned SHA-256, as `vs-lambda-converter` builds ffmpeg. A package from the base image's own repositories (`dnf`, `apt`) is fine.
- Never pipe a download into a shell (`curl ... | bash`, `wget ... | sh`) and never run an installer script fetched at build time. Install from the base image's package manager, pinning the version where the repository allows it.
- Anything that cannot be built from source (an npm package, a Docker base image, a release archive) is pinned to an exact version and a checksum or digest (`image@sha256:...`, `sha256sum -c`), and must be at least 7 days old when pinned, like the Python packages: there is no quarantine for npm, so check the publish date yourself.
- GitHub Actions are used at a release tag of their publisher (`actions/checkout@v7`), never at a branch of a third party. The one exception is Astral's `setup-uv@main`: Astral releases so often that a tag would lag within weeks.
- A pin lives in a committed file with a `just` recipe to move it (e.g. `crystal-eye-version.txt`, `ffmpeg.sha256`), so an update is a reviewed commit, and a check builds and runs what the pin produces before it is deployed.
- Our own private binaries (e.g. `crystal-eye`) come from the eye2Gene GitHub releases with `gh release download`, pinned by version and checked by the build.
- `uv audit` must pass, and a PR says why a new dependency or tool is needed and where it comes from.
