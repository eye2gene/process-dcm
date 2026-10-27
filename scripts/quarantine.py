# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Take a security fix before its 7-day quarantine ends, from one list shared by every Eye2Gene project.

Every project locks with ``exclude-newer = "7 days"``: a PyPI release is ignored until it is 7 days old. When
``uv audit`` reports a vulnerability whose fix is younger than that, the fix goes once, for the whole organisation,
into ``quarantine-exceptions.toml`` of eye2Gene/e2g-workflows. ``sync`` writes the active entries of that list to
the user-level uv configuration (``~/.config/uv/uv.toml``), which every ``uv`` command on this machine reads, so
the next ``uv lock`` admits the fix. uv records each exception it used in ``uv.lock``; ``check``, like CI, accepts
a lock only when every exception that still lets something in is in the list. An expired one, listed or not, only
draws a warning, since by then it merely pins the package; ``allow`` prunes expired entries from the list when it
adds one, and the pull requests and git history keep the record.

Run it through the justfile: ``just up`` (sync, lock, check, audit) and ``just allow <package> [<version>]``, which
opens a pull request listing the fix on e2g-workflows and arms auto-merge when that repository allows it; once the
pull request is merged, ``just up``. ``from-lock`` serves the release: the semantic-release container and the build
step re-lock without reaching the list, so they take the exceptions from the lock CI validated. The script needs only
the standard library, so ``uv run --no-project scripts/quarantine.py`` runs it without touching the project's lock.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

# ruff: noqa: S603, S607

LIST_REPO = "eye2Gene/e2g-workflows"
LIST_FILE = "quarantine-exceptions.toml"
LIST_SOURCE_VAR = "E2G_QUARANTINE_LIST"  # a path or URL that stands in for the list on main, to try it before merging
PYPI_URL = "https://pypi.org/pypi/{package}/{version}/json"
BLOCK_BEGIN = "# >>> e2g quarantine exceptions (managed: edit eye2Gene/e2g-workflows instead) >>>"
BLOCK_END = "# <<< e2g quarantine exceptions <<<"
TIMESTAMP = "%Y-%m-%dT%H:%M:%SZ"
MERGE_WAIT_SECONDS = 120
_BLOCK = re.compile(
    rf"^{re.escape(BLOCK_BEGIN)}\n.*?^{re.escape(BLOCK_END)}\n?",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class Entry:
    """One exception of the shared list: ``package`` releases uploaded up to ``cutoff`` resolve despite the quarantine."""

    package: str
    version: str
    cutoff: datetime
    advisory: str
    added: str
    by: str

    def expires(self, days: int) -> datetime:
        """Return when the global rule admits everything this entry admits, so the entry stops mattering."""
        return self.cutoff + timedelta(days=days)


@dataclass(frozen=True)
class Policy:
    """The shared list: the quarantine length, the packages that never wait, and the exceptions."""

    quarantine_days: int
    no_quarantine: frozenset[str]
    entries: tuple[Entry, ...]


@dataclass(frozen=True)
class Report:
    """How the exceptions recorded in a ``uv.lock`` relate to the shared list."""

    unquarantined: list[str]
    active: list[tuple[str, Entry]]
    expired: list[tuple[str, datetime, Entry | None]]
    unlisted: list[tuple[str, datetime | None]]


class GhError(Exception):
    """The GitHub CLI failed for a reason other than authentication."""


class MissingRelease(SystemExit):
    """PyPI answered that the release does not exist, or that it has no files: not a failed lookup."""


def normalize(name: str) -> str:
    """Return a package name as uv and PyPI write it: lower case, runs of ``-``, ``_`` and ``.`` as one ``-``."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_timestamp(value: object, *, what: str) -> datetime:
    """Return ``value``, an ISO 8601 string such as ``2026-10-19T20:13:00Z`` or a TOML date-time, as an aware UTC time."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SystemExit(f"{what}: {value!r} is not an ISO 8601 timestamp") from exc
    else:
        raise SystemExit(f"{what}: {value!r} is not a timestamp")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_timestamp(moment: datetime) -> str:
    """Return ``moment`` the way uv writes it in ``uv.lock``."""
    return moment.astimezone(UTC).strftime(TIMESTAMP)


_VERSION = re.compile(
    r"""
    ^\s*v?
    (?:(?P<epoch>\d+)!)?
    (?P<release>\d+(?:\.\d+)*)
    (?:[-_.]?(?P<pre_l>alpha|beta|preview|pre|a|b|c|rc)[-_.]?(?P<pre_n>\d*))?
    (?:-(?P<post_n1>\d+)|[-_.]?(?P<post_l>post|rev|r)[-_.]?(?P<post_n2>\d*))?
    (?:[-_.]?dev[-_.]?(?P<dev_n>\d*))?
    (?:\+(?P<local>[a-z0-9]+(?:[-_.][a-z0-9]+)*))?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)
_PRE_RANK = {
    "a": 0,
    "alpha": 0,
    "b": 1,
    "beta": 1,
    "c": 2,
    "rc": 2,
    "pre": 2,
    "preview": 2,
}
VersionKey = tuple[
    int,
    tuple[int, ...],
    tuple[int, int, int],
    tuple[int, int],
    tuple[int, int],
    tuple[tuple[int, int, str], ...],  # local segments: (1, number, "") sort after (0, 0, text), as PEP 440 says
]


def _parsed(version: str) -> re.Match[str]:
    match = _VERSION.match(version)
    if match is None:
        raise SystemExit(f"{version!r} is not a PEP 440 version")
    return match


def release_of(version: str) -> tuple[int, ...]:
    """Return the release segment of a PEP 440 version as written (5.1.14 → (5, 1, 14)), to tell branches apart."""
    return tuple(int(part) for part in _parsed(version).group("release").split("."))


def version_key(version: str) -> VersionKey:
    """Return a key that orders PEP 440 versions as pip and uv do: epoch, release, pre, post, dev and local parts.

    So ``1.2.3.dev1 < 1.2.3rc1 < 1.2.3 < 1.2.3.post1`` and ``1.0 == 1.0.0``; anything that is not a version is refused.
    """
    match = _parsed(version)
    release = release_of(version)
    while len(release) > 1 and release[-1] == 0:
        release = release[:-1]
    pre_label = match.group("pre_l")
    has_post = match.group("post_l") is not None or match.group("post_n1") is not None
    dev_number = match.group("dev_n")
    if pre_label is None and not has_post and dev_number is not None:
        pre = (-1, 0, 0)  # a dev release sorts before the pre-releases of its version
    elif pre_label is None:
        pre = (1, 0, 0)  # a final release sorts after its pre-releases
    else:
        pre = (0, _PRE_RANK[pre_label.lower()], int(match.group("pre_n") or 0))
    post = (0, int(match.group("post_n1") or match.group("post_n2") or 0)) if has_post else (-1, 0)
    dev = (0, int(dev_number or 0)) if dev_number is not None else (1, 0)
    local = match.group("local")
    local_key: tuple[tuple[int, int, str], ...] = (
        tuple((1, int(part), "") if part.isdigit() else (0, 0, part.lower()) for part in re.split(r"[-_.]", local))
        if local
        else ()
    )
    return int(match.group("epoch") or 0), release, pre, post, dev, local_key


def _string(table: dict[str, object], key: str, *, what: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"{what}: {key} must be a non-empty string, got {value!r}")
    return value


def load_policy(text: str) -> Policy:
    """Parse the shared list, refusing anything malformed rather than guessing."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"{LIST_FILE} is not valid TOML: {exc}") from exc
    policy = data.get("policy")
    if not isinstance(policy, dict):
        raise SystemExit(f"{LIST_FILE}: missing [policy] table")
    days = policy.get("quarantine-days")
    if not isinstance(days, int) or days <= 0:
        raise SystemExit(f"{LIST_FILE}: [policy] quarantine-days must be a positive integer, got {days!r}")
    no_quarantine = policy.get("no-quarantine", [])
    if not isinstance(no_quarantine, list) or not all(isinstance(name, str) for name in no_quarantine):
        raise SystemExit(f"{LIST_FILE}: [policy] no-quarantine must be a list of package names")
    raw_entries = data.get("exception", [])
    if not isinstance(raw_entries, list):
        raise SystemExit(f"{LIST_FILE}: exception must be an array of tables ([[exception]])")
    entries: list[Entry] = []
    for index, raw in enumerate(raw_entries, start=1):
        what = f"{LIST_FILE}: [[exception]] #{index}"
        if not isinstance(raw, dict):
            raise SystemExit(f"{what} is not a table")
        entries.append(
            Entry(
                package=normalize(_string(raw, "package", what=what)),
                version=_string(raw, "version", what=what),
                cutoff=parse_timestamp(raw.get("cutoff"), what=f"{what} cutoff"),
                advisory=str(raw.get("advisory", "")),
                added=str(raw.get("added", "")),
                by=str(raw.get("by", "")),
            )
        )
    return Policy(
        quarantine_days=days,
        no_quarantine=frozenset(normalize(str(name)) for name in no_quarantine),
        entries=tuple(entries),
    )


def lock_exceptions(lock_text: str) -> dict[str, datetime | None]:
    """Return the exceptions uv recorded in ``uv.lock``: package to cutoff, or None where it is not quarantined at all."""
    options = tomllib.loads(lock_text).get("options")
    table = options.get("exclude-newer-package") if isinstance(options, dict) else None
    if not isinstance(table, dict):
        return {}
    exceptions: dict[str, datetime | None] = {}
    for name, value in table.items():
        exceptions[normalize(name)] = (
            None if value is False else parse_timestamp(value, what=f"uv.lock exclude-newer-package {name}")
        )
    return exceptions


def active_exceptions(policy: Policy, now: datetime) -> dict[str, datetime | None]:
    """Return what the user-level uv configuration should hold now: unexpired entries and the packages that never wait."""
    exceptions: dict[str, datetime | None] = {}
    for entry in policy.entries:
        if now >= entry.expires(policy.quarantine_days):
            continue
        previous = exceptions.get(entry.package)
        if previous is None or entry.cutoff > previous:
            exceptions[entry.package] = entry.cutoff
    for name in policy.no_quarantine:
        exceptions[name] = None
    return dict(sorted(exceptions.items()))


def classify(lock: dict[str, datetime | None], policy: Policy, now: datetime) -> Report:
    """Sort a lock's exceptions: active and listed, expired (listed or not), or unlisted while still letting something in."""
    report = Report([], [], [], [])
    for name, cutoff in lock.items():
        if cutoff is None:
            if name in policy.no_quarantine:
                report.unquarantined.append(name)
            else:
                report.unlisted.append((name, None))
            continue
        covering = [entry for entry in policy.entries if entry.package == name and entry.cutoff >= cutoff]
        entry = min(covering, key=lambda candidate: candidate.cutoff) if covering else None
        if now >= cutoff + timedelta(days=policy.quarantine_days):
            report.expired.append((name, cutoff, entry))
        elif entry is None:
            report.unlisted.append((name, cutoff))
        else:
            report.active.append((name, entry))
    return report


def user_config_path() -> Path:
    """Return the user-level uv configuration file, the one every ``uv`` command on this machine reads."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "uv" / "uv.toml"


def render_block(exceptions: dict[str, datetime | None]) -> str:
    """Return the managed block of the user-level configuration, empty when there is nothing to allow."""
    if not exceptions:
        return ""
    items = ", ".join(
        f"{name} = false" if cutoff is None else f'{name} = "{format_timestamp(cutoff)}"'
        for name, cutoff in sorted(exceptions.items())
    )
    return f"{BLOCK_BEGIN}\nexclude-newer-package = {{ {items} }}\n{BLOCK_END}\n"


def merge_config(existing: str, exceptions: dict[str, datetime | None]) -> str:
    """Return ``existing`` with its managed block replaced (at the top, where a top-level key is always valid)."""
    rest = _BLOCK.sub("", existing).lstrip("\n")
    block = render_block(exceptions)
    merged = f"{block}\n{rest}" if block and rest else block + rest
    try:
        tomllib.loads(merged)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(
            f"{user_config_path()} would not be valid TOML with the managed block ({exc}); "
            "it probably sets exclude-newer-package itself: remove that, the shared list replaces it"
        ) from exc
    return merged


def write_user_config(exceptions: dict[str, datetime | None]) -> Path:
    """Write the managed block to the user-level uv configuration, keeping whatever else is in the file."""
    path = user_config_path()
    existing = path.read_text() if path.exists() else ""
    merged = merge_config(existing, exceptions)
    if merged.strip():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(merged)
    elif path.exists():
        path.unlink()
    return path


def pypi_cutoff(release: dict[str, object]) -> datetime:
    """Return one minute after the last file of a PyPI release was uploaded, so every file of that version resolves."""
    urls = release.get("urls")
    uploads = [
        parse_timestamp(file.get("upload_time_iso_8601"), what="PyPI upload time")
        for file in (urls if isinstance(urls, list) else [])
        if isinstance(file, dict)
    ]
    if not uploads:
        raise MissingRelease("PyPI lists no files for that release")
    return (max(uploads) + timedelta(minutes=1)).replace(microsecond=0)


def release_cutoff(package: str, version: str) -> datetime:
    """Return the cutoff that admits every file of ``package`` ``version``, read from PyPI.

    Raises ``MissingRelease`` only when PyPI says the release is not there; any other failure stops the script.
    """
    try:
        release = json.loads(fetch_text(PYPI_URL.format(package=package, version=version)))
    except MissingRelease as exc:
        raise MissingRelease(f"PyPI has no {package} {version}: {exc}") from exc
    except SystemExit as exc:
        raise SystemExit(f"could not read {package} {version} from PyPI: {exc}") from exc
    return pypi_cutoff(release)


def fixed_by(candidate: str, fixes: list[str]) -> bool:
    """Return whether ``candidate`` carries one of ``fixes``.

    A finding names one fix per maintenance branch (4.2.26, 5.1.14 and 5.2.8, or 1.9.9 and 2.0.2). The branches are
    told apart one version component at a time: at each component in which the fixes in play still differ, only those
    sharing the candidate's value stay in play, so 5.2.4 is measured against 5.2.8 alone, not against the 5.x pair.
    A candidate is fixed when it is at or above the fix of its own branch, or above every fix in play when its branch
    has none (5.3.0 and 6.0 carry the fixes above; 3.9 does not).
    """
    if not fixes:
        return False
    key = version_key(candidate)
    release = release_of(candidate)
    group = list(fixes)
    depth = 0
    while True:
        releases = [release_of(fix) for fix in group]
        split = next(
            (
                index
                for index in range(depth, min(len(each) for each in releases))
                if len({each[index] for each in releases}) > 1
            ),
            None,
        )
        if split is None:
            return key >= min(version_key(fix) for fix in group)
        same = [fix for fix, each in zip(group, releases, strict=True) if each[: split + 1] == release[: split + 1]]
        if not same:
            return key >= max(version_key(fix) for fix in group)
        group, depth = same, split + 1


def _findings(audit: dict[str, object], package: str) -> tuple[list[tuple[list[str], VersionKey | None]], list[str]]:
    """Return the fixes each ``uv audit`` finding for ``package`` names with the version it found, and the advisory IDs.

    A lock can hold several versions of one package (one per Python version or platform fork), so each finding keeps
    its own.
    """
    findings: list[tuple[list[str], VersionKey | None]] = []
    advisories: list[str] = []
    vulnerabilities = audit.get("vulnerabilities")
    for vulnerability in vulnerabilities if isinstance(vulnerabilities, list) else []:
        if not isinstance(vulnerability, dict):
            continue
        dependency = vulnerability.get("dependency")
        if not isinstance(dependency, dict) or normalize(str(dependency.get("name", ""))) != package:
            continue
        fixes = vulnerability.get("fix_versions")
        fixes = [str(fix) for fix in fixes] if isinstance(fixes, list) else []
        if not fixes:
            continue
        locked_version = str(dependency.get("version", ""))
        findings.append((fixes, version_key(locked_version) if locked_version else None))
        advisories.append(str(vulnerability.get("id", "")))
    return findings, advisories


def audit_fix(audit: dict[str, object], package: str) -> tuple[str, str] | None:
    """Return the lowest version at or above the locked one that fixes every ``uv audit`` finding for ``package``, with the advisory IDs."""
    found, advisories = _findings(audit, package)
    if not found:
        return None
    findings = [fixes for fixes, _ in found]
    locked = max((each for _, each in found if each is not None), default=None)
    # The lowest release at or above the locked version that carries a fix for every finding; when no single
    # release does (or the audit's fixes are all below the locked version), the newest fix named.
    candidates = sorted(
        {fix for fixes in findings for fix in fixes if locked is None or version_key(fix) >= locked},
        key=version_key,
    )
    chosen = next(
        (candidate for candidate in candidates if all(fixed_by(candidate, fixes) for fixes in findings)),
        None,
    )
    if chosen is None:
        chosen = max((fix for fixes in findings for fix in fixes), key=version_key)
    return chosen, ", ".join(sorted(set(advisories)))


def run_audit() -> dict[str, object]:
    """Return the ``uv audit`` report for the project in the current directory.

    A report counts whatever the exit code, since findings make it non-zero; no report means the audit failed (no
    network, a broken lock), and an empty one would let ``allow`` go on without the fixes it widens the cutoff over.
    """
    audit = subprocess.run(
        ["uv", "audit", "--output-format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(audit.stdout)
    except json.JSONDecodeError:
        report = None
    if not isinstance(report, dict) or not isinstance(report.get("vulnerabilities"), list):
        detail = audit.stderr.strip().splitlines()[-1] if audit.stderr.strip() else f"exit {audit.returncode}"
        raise SystemExit(f"uv audit failed, so `allow` cannot see the fixes it reports: {detail}")
    return report


def fixes_ahead(audit: dict[str, object], package: str) -> list[str]:
    """Return every fix the ``uv audit`` findings for ``package`` name at or above the version each found, oldest first.

    These are the releases ``uv lock -U`` may move to, one per maintenance branch the constraints could allow; with
    4.2.25 and 5.2.7 both locked, 4.2.26 is one of them as much as 5.2.8.
    """
    found, _ = _findings(audit, package)
    return sorted(
        {fix for fixes, locked in found for fix in fixes if locked is None or version_key(fix) >= locked},
        key=version_key,
    )


def render_entry(entry: Entry) -> str:
    """Return ``entry`` as the TOML table that goes at the end of the shared list."""
    return (
        "\n[[exception]]\n"
        f'package = "{entry.package}"\n'
        f'version = "{entry.version}"\n'
        f'cutoff = "{format_timestamp(entry.cutoff)}"\n'
        f'advisory = "{entry.advisory}"\n'
        f'added = "{entry.added}"\n'
        f'by = "{entry.by}"\n'
    )


def describe(name: str, entry: Entry, days: int) -> str:
    """Return one line about an active exception."""
    return (
        f"{name}: releases up to {format_timestamp(entry.cutoff)} allowed "
        f"({entry.version}, {entry.advisory or 'no advisory recorded'}; expires {entry.expires(days):%Y-%m-%d})"
    )


def describe_expired(name: str, cutoff: datetime, entry: Entry | None, days: int) -> str:
    """Return one line about an exception a lock still carries past its expiry, listed or not."""
    about = f"{entry.version}, {entry.advisory or 'no advisory recorded'}" if entry else "no longer in the list"
    return (
        f"{name}: releases up to {format_timestamp(cutoff)} allowed ({about}; "
        f"expired {cutoff + timedelta(days=days):%Y-%m-%d}): it now only pins {name}; `just up` drops it"
    )


def updated_list(text: str, policy: Policy, entry: Entry, now: datetime) -> str:
    """Return the list with ``entry`` appended and the expired entries pruned; the header and [policy] stay as written.

    An entry for the same package and version, which ``entry`` widens, goes too: the list holds one per pair.
    """
    head, _, _ = text.partition("\n[[exception]]\n")
    kept = [
        old
        for old in policy.entries
        if now < old.expires(policy.quarantine_days) and (old.package, old.version) != (entry.package, entry.version)
    ]
    return head.rstrip("\n") + "\n" + "".join(render_entry(each) for each in [*kept, entry])


def fetch_text(source: str) -> str:
    """Return the content of a local file or an https URL."""
    if source.startswith("https://"):
        try:
            with urllib.request.urlopen(source, timeout=30) as response:  # noqa: S310 - https only, checked above
                return response.read().decode()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise MissingRelease(f"{source} was not found") from exc
            raise SystemExit(f"could not fetch {source}: {exc}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise SystemExit(f"could not fetch {source}: {exc}") from exc
    path = Path(source)
    if not path.is_file():
        raise SystemExit(f"{source} is neither an https URL nor a file")
    return path.read_text()


def gh(*args: str) -> str:
    """Run the GitHub CLI and return its output, stopping with instructions when it is missing or logged out."""
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise SystemExit("the GitHub CLI (gh) is not installed: https://cli.github.com") from exc
    if result.returncode != 0:
        error = result.stderr.strip()
        if any(
            hint in error
            for hint in (
                "gh auth login",
                "Bad credentials",
                "HTTP 401",
                "not logged in",
            )
        ):
            raise SystemExit("the GitHub CLI is not logged in, or its token expired: run `gh auth login`, then retry")
        raise GhError(error or f"gh {' '.join(args)} failed")
    return result.stdout.strip()


def fetch_list() -> tuple[str, str]:
    """Return the shared list and its blob SHA (empty when it came from the ``E2G_QUARANTINE_LIST`` override)."""
    override = os.environ.get(LIST_SOURCE_VAR)
    if override:
        return fetch_text(override), ""
    meta = json.loads(gh("api", f"repos/{LIST_REPO}/contents/{LIST_FILE}?ref=main"))
    return base64.b64decode(meta["content"]).decode(), str(meta["sha"])


def cmd_sync(now: datetime) -> int:
    """Write the active exceptions of the shared list to the user-level uv configuration."""
    text, _ = fetch_list()
    policy = load_policy(text)
    exceptions = active_exceptions(policy, now)
    path = write_user_config(exceptions)
    if not exceptions:
        print(f"no active quarantine exceptions: {path} holds none")
        return 0
    print(f"quarantine exceptions written to {path}:")
    for name, cutoff in exceptions.items():
        if cutoff is None:
            print(f"  {name}: never quarantined (Eye2Gene package)")
            continue
        entry = next(e for e in policy.entries if e.package == name and e.cutoff == cutoff)
        print(f"  {describe(name, entry, policy.quarantine_days)}")
    return 0


def cmd_from_lock() -> int:
    """Write the exceptions ``uv.lock`` records to the user-level uv configuration, so a re-lock keeps them.

    For environments that re-lock a lock CI has already validated and that cannot reach the shared list: the
    semantic-release container, whose ``build_command`` bumps the version in the lock, and the build step after it.
    """
    lock_path = Path("uv.lock")
    lock = lock_exceptions(lock_path.read_text()) if lock_path.is_file() else {}
    path = write_user_config(lock)
    if not lock:
        print(f"uv.lock records no quarantine exceptions: {path} holds none")
        return 0
    print(f"{len(lock)} quarantine exception(s) of uv.lock written to {path}: {', '.join(lock)}")
    return 0


def cmd_check(now: datetime) -> int:
    """Refuse a ``uv.lock`` that lets a package in early without an entry in the shared list, as CI does."""
    lock_path = Path("uv.lock")
    if not lock_path.is_file():
        print("no uv.lock to check")
        return 0
    lock = lock_exceptions(lock_path.read_text())
    if not lock:
        print("uv.lock records no quarantine exceptions")
        return 0
    text, _ = fetch_list()
    policy = load_policy(text)
    report = classify(lock, policy, now)
    for name in report.unquarantined:
        print(f"{name}: never quarantined (Eye2Gene package)")
    for name, entry in report.active:
        print(describe(name, entry, policy.quarantine_days))
    for name, cutoff, entry in report.expired:
        print(f"warning: {describe_expired(name, cutoff, entry, policy.quarantine_days)}")
    for name, cutoff in report.unlisted:
        allowed = "without any quarantine" if cutoff is None else f"up to {format_timestamp(cutoff)}"
        print(f"error: uv.lock lets {name} in {allowed}, which {LIST_FILE} in {LIST_REPO} does not allow")
    if not report.unlisted:
        return 0
    print(
        "list the fix with `just allow <package> [<version>]`; if pyproject.toml sets exclude-newer-package, "
        "remove it, the shared list replaces it, then run `just up`"
    )
    return 1


def wait_for_merge(pr_url: str) -> bool:
    """Return whether the pull request merged within the wait, polling GitHub a few times."""
    deadline = time.monotonic() + MERGE_WAIT_SECONDS
    while time.monotonic() < deadline:
        if (
            gh(
                "pr",
                "view",
                pr_url,
                "-R",
                LIST_REPO,
                "--json",
                "state",
                "--jq",
                ".state",
            )
            == "MERGED"
        ):
            return True
        time.sleep(5)
    return False


def cmd_allow(package_arg: str, version_arg: str, now: datetime) -> int:
    """Open a pull request that lists a security fix on e2g-workflows, auto-merged when the repository allows it."""
    package = normalize(package_arg)
    gh("auth", "status")
    report = run_audit()
    if version_arg:
        version, advisory = version_arg, ""
    else:
        fix = audit_fix(report, package)
        if fix is None:
            raise SystemExit(
                f"uv audit reports no fix for {package}: name the version, `just allow {package} <version>`"
            )
        version, advisory = fix
    # A named version gets the same widening: the audit's other fixes for the package, if it reports any.
    others = [each for each in fixes_ahead(report, package) if each != version]
    cutoff = release_cutoff(package, version)
    # A cutoff that admits only the chosen fix can admit a newer, still vulnerable release of another branch (with
    # 4.2.25 locked, 4.2.26's cutoff may let 5.2.7 in when 5.2.8 came later), and `uv lock -U` would take it. So the
    # cutoff covers every fix at or above the locked version: on whichever branch the constraints allow, its fix is in.
    latest = version
    for other in others:
        try:
            other_cutoff = release_cutoff(package, other)
        except MissingRelease:
            continue  # a fix the advisory names that PyPI does not have (yet); a failed lookup stops instead
        if other_cutoff > cutoff:
            cutoff, latest = other_cutoff, other
    text, sha = fetch_list()
    policy = load_policy(text)
    expires = cutoff + timedelta(days=policy.quarantine_days)
    if now >= expires:
        print(f"{package} {version} left quarantine on {expires:%Y-%m-%d}: `just up` takes it without an exception")
        return 0
    # Listed already only when that entry's cutoff covers this one: a narrower one (from before a later branch's fix
    # was out) is replaced by a wider entry.
    for entry in policy.entries:
        if entry.package == package and entry.version == version and entry.cutoff >= cutoff:
            print(f"{package} {version} is already listed by {entry.by} on {entry.added}: `just up` takes it")
            return 0
    if not sha:
        raise SystemExit(f"{LIST_SOURCE_VAR} is set: `allow` only adds to the list on {LIST_REPO}")
    entry = Entry(
        package,
        version,
        cutoff,
        advisory,
        now.strftime("%Y-%m-%d"),
        gh("api", "user", "--jq", ".login"),
    )
    new_text = updated_list(text, policy, entry, now)
    load_policy(new_text)
    pruned = [old for old in policy.entries if now >= old.expires(policy.quarantine_days)]
    replaced = [old for old in policy.entries if (old.package, old.version) == (package, version) and old not in pruned]
    message = f"chore(quarantine): allow {package} {version}" + (f" for {advisory}" if advisory else "")
    body = (
        f"Lets `{package}` releases uploaded up to {format_timestamp(cutoff)} resolve before the "
        f"{policy.quarantine_days}-day quarantine ends, so every project can take {version}"
        + (f", which fixes {advisory}" if advisory else "")
        + (
            f"; the cutoff also admits {latest}, the last fix uploaded, so a project on another branch gets its own"
            if latest != version
            else ""
        )
        + f".\n\nThe entry expires on {expires:%Y-%m-%d}; the next `just up` of each project drops it then, "
        "and the next `just allow` prunes it from the list.\n\n"
        + "".join(
            f"Replaces the entry of {old.added} by {old.by}, whose cutoff "
            f"({format_timestamp(old.cutoff)}) left out a later fix.\n\n"
            for old in replaced
        )
        + (
            "Pruned, expired: " + ", ".join(f"{old.package} {old.version}" for old in pruned) + ".\n\n"
            if pruned
            else ""
        )
        + f"Opened by `just allow` from {Path.cwd().name}."
    )
    branch = f"allow/{package}-{version}-{now:%Y%m%dT%H%M%SZ}"
    main_sha = gh("api", f"repos/{LIST_REPO}/git/ref/heads/main", "--jq", ".object.sha")
    gh(
        "api",
        "-X",
        "POST",
        f"repos/{LIST_REPO}/git/refs",
        "-f",
        f"ref=refs/heads/{branch}",
        "-f",
        f"sha={main_sha}",
    )
    content = base64.b64encode(new_text.encode()).decode()
    gh(
        "api", "-X", "PUT", f"repos/{LIST_REPO}/contents/{LIST_FILE}",
        "-f", f"message={message}", "-f", f"content={content}", "-f", f"sha={sha}", "-f", f"branch={branch}",
    )  # fmt: skip
    pr_url = gh(
        "pr",
        "create",
        "-R",
        LIST_REPO,
        "-H",
        branch,
        "-B",
        "main",
        "-t",
        message,
        "-b",
        body,
    )
    listed = f"listed {package} {version} (cutoff {format_timestamp(cutoff)}, expires {expires:%Y-%m-%d})"
    # `gh pr merge --auto` merges an already mergeable pull request at once, so the repository setting decides
    # whether a reviewer merges it or the tool does.
    if gh("api", f"repos/{LIST_REPO}", "--jq", ".allow_auto_merge") != "true":
        print(f"{listed}: review and merge {pr_url}, then run `just up`")
        return 0
    try:
        gh("pr", "merge", pr_url, "-R", LIST_REPO, "--squash", "--auto")
    except GhError as exc:
        raise SystemExit(
            f"{listed}: {pr_url} is open, but auto-merge could not be armed ({exc}): merge it, then run `just up`"
        ) from exc
    if wait_for_merge(pr_url):
        print(f"{listed}: {pr_url} merged; now run `just up`")
    else:
        print(f"{listed}: auto-merge armed on {pr_url}, it merges once the check passes; then run `just up`")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the command line and run one of ``sync``, ``check`` or ``allow``."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "sync",
        help="write the active exceptions of the shared list to the user-level uv config",
    )
    commands.add_parser(
        "check",
        help="refuse a uv.lock whose exceptions are not in the shared list, as CI does",
    )
    commands.add_parser(
        "from-lock",
        help="write the exceptions uv.lock records to the user-level uv config (release container, build step)",
    )
    allow = commands.add_parser(
        "allow",
        help="open a pull request that lists a security fix org-wide; once merged, `just up`",
    )
    allow.add_argument("package")
    allow.add_argument("version", nargs="?", default="", help="defaults to the fix uv audit names")
    args = parser.parse_args(argv)
    now = datetime.now(UTC)
    try:
        if args.command == "sync":
            return cmd_sync(now)
        if args.command == "check":
            return cmd_check(now)
        if args.command == "from-lock":
            return cmd_from_lock()
        return cmd_allow(args.package, args.version, now)
    except GhError as exc:
        raise SystemExit(f"gh failed: {exc}") from exc


if __name__ == "__main__":
    sys.exit(main())
