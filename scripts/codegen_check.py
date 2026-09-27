"""codegen_check.py — the offline drift gate for Pipelex-generated Python trees.

Copied verbatim into a project by /pipelex-integrate. Run it from the project root, with the project's
own environment (the one `pipelex-sdk` is installed in), and one generated directory per argument:

    uv run python scripts/codegen_check.py src/my_app/generated/summarize_pdf src/my_app/generated/extract_entities

For each directory it (1) runs `pipelex-sdk`'s `run_codegen_check` over the stamped files against
`codegen.lock` — pure hashing, no engine, no network, no API key, and no `pipelex` runtime — and (2)
compares the SHA-256 recorded for each .mthds source in `sources.json` against the file on disk, and the
recorded sources against every .mthds file under the sidecar's `bundle_dir`, which is what the call site
loads, so a bundle changed without a regeneration — a file edited, removed or added — is caught as
`stale-source`.

Exit codes: 0 current · 1 drift or stale source · 2 no verdict (no lock, a malformed or unreadable lock
or tree, a symlink at the generated directory or on an artifact's path, a check that raises, `pipelex-sdk`
not importable or failing while it loads). Precedence across directories: 2 > 1 > 0.

It is the twin of `codegen-check.mjs`, which does the same for a TypeScript project over `@pipelex/sdk`,
and the two fail closed on the same malformed sidecars. It imports only the standard library and
`pipelex-sdk` (0.10.2 or later), and writes through `sys.stdout` / `sys.stderr` so a no-print lint rule
stays quiet. When `pipelex-sdk` ships this check as a command, replace this file with that one line.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import posixpath
import stat
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import NamedTuple, NoReturn, cast

try:
    from pipelex_sdk.codegen_check import run_codegen_check
    from pipelex_sdk.errors import CodegenLockError
except ImportError as import_error:
    # A gate that cannot run has no verdict to give. Letting the import fail would exit 1, which reads as
    # drift, and the likeliest cause is an interpreter outside the project's environment, not the tree.
    sys.stderr.write(
        f"codegen-check: no verdict — pipelex-sdk 0.10.2 or later is not importable ({import_error}). "
        "Run this script with the project's own environment, e.g. `uv run python scripts/codegen_check.py …`.\n"
    )
    sys.exit(2)  # EXIT_NO_VERDICT, which a linter will not let this file define above its imports
except Exception as load_error:
    # The one place this script meets an SDK whose exception surface at import is open-ended: a pydantic
    # whose pydantic-core does not match it raises `SystemError`, a corrupt SDK file `SyntaxError`. Uncaught,
    # any of them exits 1 — drift — over a tree nobody checked. `BaseException` is left alone, so an
    # interrupt stays an interrupt. `_describe` is defined below the imports, so its format is inlined.
    sys.stderr.write(
        f"codegen-check: no verdict — pipelex-sdk failed while loading ({type(load_error).__name__}: {load_error}). "
        "The project's environment looks broken: reinstall its dependencies, e.g. `uv sync --reinstall`; "
        "running the script under another interpreter will not fix it.\n"
    )
    sys.exit(2)  # EXIT_NO_VERDICT

EXIT_CURRENT = 0
EXIT_DRIFT = 1
EXIT_NO_VERDICT = 2

LOCK_FILENAME = "codegen.lock"
SIDECAR_FILENAME = "sources.json"
NO_SOURCES_LINE = f"  {SIDECAR_FILENAME} records no sources — a by-ref or by-id integration; source staleness does not apply"


class Outcome(NamedTuple):
    """One check's exit code and the lines explaining it."""

    code: int
    lines: tuple[str, ...]


class Recorded(NamedTuple):
    """What a sidecar recorded about a local bundle: its sources as sorted pairs, and the directory the call site loads."""

    sources: list[tuple[str, object]]
    bundle_dir: str


class Bundle(NamedTuple):
    """The .mthds files the call site loads, each normalized path mapped to the path shown for it.

    `paths` is None when the directory cannot be listed, and `lines` then says why.
    """

    paths: dict[Path, str] | None
    lines: tuple[str, ...]


def _out(line: str) -> None:
    sys.stdout.write(f"{line}\n")
    # Flushed line by line: under CI and `make` stdout is a block-buffered pipe, so without this a
    # directory's name would print after the drift lines that went to stderr about it.
    sys.stdout.flush()


def _err(line: str) -> None:
    sys.stderr.write(f"{line}\n")
    sys.stderr.flush()


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _reject_json_constant(value: str) -> NoReturn:
    # Python's `json` accepts `NaN`, `Infinity` and `-Infinity`; JSON does not, and neither does the
    # TypeScript twin's `JSON.parse`. A sidecar only this reader could parse is an unreadable sidecar.
    msg = f"non-standard JSON constant {value}"
    raise ValueError(msg)


def check_tree(*, directory: Path) -> Outcome:
    """Run the lock check. A state of the tree never raises: it is a verdict, or the absence of one."""
    try:
        report = run_codegen_check(root=directory)
    except CodegenLockError as exc:
        return Outcome(code=EXIT_NO_VERDICT, lines=(f"  no verdict: {exc}",))
    if not report.lock_found:
        # The SDK asks `is_file()`, which on recent Pythons answers `False` for a lock behind a directory the
        # process cannot search as well as for one that is absent. Only an absent lock is "not found"; asking
        # again with `lstat` raises anything else, and `settle` reports it for what it is.
        try:
            (directory / LOCK_FILENAME).lstat()
        except (FileNotFoundError, NotADirectoryError):
            pass
        return Outcome(code=EXIT_NO_VERDICT, lines=(f"  no verdict: {LOCK_FILENAME} — not found",))
    if report.is_current:
        fingerprint = (report.crate_fingerprint or "")[:12]
        return Outcome(code=EXIT_CURRENT, lines=(f"  tree current (crate {fingerprint}, engine {report.engine_version})",))
    return Outcome(code=EXIT_DRIFT, lines=tuple(f"  {drift.category}: {drift.path} — {drift.detail}" for drift in report.drifts))


def check_sources(*, directory: Path) -> Outcome:
    """Run the sidecar check: each recorded .mthds source and the bundle directory, by their paths relative to the project root."""
    try:
        # Strict UTF-8 over the raw bytes, and deliberately not `utf-8-sig`: a byte-order mark stays in the
        # text, so `json.loads` refuses it exactly as the TypeScript twin's `JSON.parse` does. Handing
        # `json.loads` the bytes instead would sniff the mark and strip it, and a sidecar the other gate calls
        # unreadable would pass here.
        text = (directory / SIDECAR_FILENAME).read_bytes().decode("utf-8")
        sidecar: object = json.loads(text, parse_constant=_reject_json_constant)
    except FileNotFoundError:
        return Outcome(code=EXIT_CURRENT, lines=(f"  no {SIDECAR_FILENAME} — source staleness not checked",))
    except (OSError, ValueError, RecursionError) as exc:
        # `UnicodeDecodeError` and `json.JSONDecodeError` are both `ValueError`s.
        return Outcome(code=EXIT_DRIFT, lines=(f"  stale-source: {SIDECAR_FILENAME} — unreadable ({exc}), so staleness cannot be ruled out",))
    recorded = _recorded_sources(sidecar=sidecar)
    if isinstance(recorded, Outcome):
        return recorded
    return _compare_sources(recorded=recorded)


def _recorded_sources(*, sidecar: object) -> Recorded | Outcome:
    """Return the sidecar's `sources` and `bundle_dir`, or the outcome that ends the check before any source is read."""
    # A file whose whole content is `null`, `[]`, `"x"`, `42` or `true` is valid JSON and not an object. Read
    # through `.get()` or a truthiness test, every one of them looks like the legitimate absent case, and the
    # gate would announce "a by-ref or by-id integration" and exit 0 over a sidecar that says nothing of the
    # kind. So the sidecar is guarded first, and its `sources` second.
    if not isinstance(sidecar, dict):
        return Outcome(code=EXIT_DRIFT, lines=(f"  stale-source: {SIDECAR_FILENAME} — not a JSON object, so staleness cannot be ruled out",))
    fields = cast("dict[str, object]", sidecar)

    # A present-but-wrong-shaped `sources` must fail the way an unreadable sidecar does. Coerced to `{}` it
    # would check nothing, print nothing and exit 0 — the one input that is both silent and green. An explicit
    # `null` is why presence is tested with `in` rather than by reading the value: `None` is not absent.
    if "sources" not in fields and "bundle_dir" not in fields:
        return Outcome(code=EXIT_CURRENT, lines=(NO_SOURCES_LINE,))
    sources = fields.get("sources")
    if not isinstance(sources, dict):
        return Outcome(code=EXIT_DRIFT, lines=(f"  stale-source: {SIDECAR_FILENAME} — `sources` is not an object, so staleness cannot be ruled out",))
    recorded_sources = sorted(cast("dict[str, object]", sources).items())
    if not recorded_sources and "bundle_dir" not in fields:
        return Outcome(code=EXIT_CURRENT, lines=(NO_SOURCES_LINE,))
    # The hashes alone prove only that the recorded files are unchanged. The call site loads every .mthds file
    # under its bundle directory, so a file added beside them changes what runs while every recorded hash still
    # matches: without the directory, that addition cannot be ruled out.
    if "bundle_dir" not in fields:
        return Outcome(
            code=EXIT_DRIFT,
            lines=(
                f"  stale-source: {SIDECAR_FILENAME} — records sources but no `bundle_dir`, so a .mthds file added to the bundle cannot be ruled out",
            ),
        )
    bundle_dir = fields["bundle_dir"]
    if not isinstance(bundle_dir, str) or not bundle_dir:
        return Outcome(
            code=EXIT_DRIFT, lines=(f"  stale-source: {SIDECAR_FILENAME} — `bundle_dir` is not a non-empty string, so staleness cannot be ruled out",)
        )
    return Recorded(sources=recorded_sources, bundle_dir=bundle_dir)


def _normalized(path: Path) -> Path:
    """The absolute path with `.` and `..` collapsed lexically, as the TypeScript twin's `path.resolve` does: no symlink is followed."""
    return Path(os.path.normpath(path.absolute()))


def _compare_sources(*, recorded: Recorded) -> Outcome:
    """Hash each recorded source on disk against the SHA-256 the sidecar recorded, and match the recorded set against the bundle's."""
    project_root = Path.cwd()
    bundle = _list_bundle(project_root=project_root, bundle_dir=recorded.bundle_dir)
    stale_lines: list[str] = list(bundle.lines)
    recorded_paths: set[Path] = set()
    for source, recorded_hash in recorded.sources:
        resolved = _normalized(project_root / source)
        recorded_paths.add(resolved)
        try:
            on_disk = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except FileNotFoundError:
            stale_lines.append(f"  stale-source: {source} — recorded as a source but no longer on disk")
            continue
        except (OSError, ValueError) as exc:
            stale_lines.append(f"  stale-source: {source} — recorded as a source but unreadable ({exc})")
            continue
        if on_disk != recorded_hash:
            stale_lines.append(f"  stale-source: {source} — edited since the types were generated")
        elif bundle.paths is not None and resolved not in bundle.paths:
            stale_lines.append(
                f"  stale-source: {source} — recorded as a source but not under {recorded.bundle_dir}, so the call site does not load it"
            )
    if bundle.paths is not None:
        for resolved, shown in bundle.paths.items():
            if resolved not in recorded_paths:
                stale_lines.append(f"  stale-source: {shown} — added to the bundle since the types were generated")
    return Outcome(code=EXIT_DRIFT if stale_lines else EXIT_CURRENT, lines=tuple(stale_lines))


def _list_bundle(*, project_root: Path, bundle_dir: str) -> Bundle:
    """List the .mthds files the call site loads, the way it lists them: `rglob("*.mthds")` under the bundle directory."""
    root = project_root / bundle_dir
    # Asked first because `rglob` answers a missing directory and a file alike with an empty list, while the
    # TypeScript twin's `readdir` raises for both; asking here makes the two gates say the same thing.
    try:
        root_stat = root.stat()
    except FileNotFoundError:
        return Bundle(paths=None, lines=(f"  stale-source: {bundle_dir} — recorded as the bundle directory but no longer on disk",))
    except (OSError, ValueError) as exc:
        return Bundle(paths=None, lines=(f"  stale-source: {bundle_dir} — recorded as the bundle directory but unreadable ({exc})",))
    if not stat.S_ISDIR(root_stat.st_mode):
        return Bundle(paths=None, lines=(f"  stale-source: {bundle_dir} — recorded as the bundle directory but not a directory",))
    shown_by_path = {
        _normalized(match): posixpath.normpath(posixpath.join(bundle_dir, match.relative_to(root).as_posix())) for match in root.rglob("*.mthds")
    }
    # Ordered by the path shown, which is how the TypeScript twin orders them; `Path` ordering compares parts.
    paths = dict(sorted(shown_by_path.items(), key=lambda item: item[1]))
    if not paths:
        return Bundle(paths=paths, lines=(f"  stale-source: {bundle_dir} — holds no .mthds file, so the call site has no bundle to load",))
    return Bundle(paths=paths, lines=())


def settle(*, name: str, check: Callable[[], Outcome]) -> Outcome:
    """Run one check over one directory, turning anything it raises into no verdict for that directory.

    Each check already turns every state of the tree it knows into an outcome. Whatever else escapes — a lock
    `tomllib` refuses with a `ValueError`, nesting deep enough for a `RecursionError`, a `PermissionError` the
    SDK does not wrap — says nothing about the tree. Uncaught, it would end the whole run with exit 1, which
    reads as drift, and every directory after it would go unchecked; here, the precedence decides the exit code.
    """
    try:
        return check()
    except Exception as exc:
        # The root of the command for one directory, around an SDK check whose exception surface is open-ended.
        return Outcome(code=EXIT_NO_VERDICT, lines=(f"  no verdict: the {name} check failed — {_describe(exc)}",))


def worse(first: int, second: int) -> int:
    """Precedence: no verdict > drift > current."""
    if EXIT_NO_VERDICT in (first, second):
        return EXIT_NO_VERDICT
    if EXIT_DRIFT in (first, second):
        return EXIT_DRIFT
    return EXIT_CURRENT


def main(argv: list[str]) -> int:
    """Check every generated directory named on the command line and return the worst exit code."""
    # A line this script writes must never be what fails it. Under a locale whose encoding lacks a character
    # it prints (the em dash, or a directory name holding an undecodable byte), a strict stream raises
    # `UnicodeEncodeError` and a current tree exits 1; escaping the character keeps the verdict.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    arguments = argv[1:]
    if not arguments:
        _err("usage: python scripts/codegen_check.py <generated-dir> [<generated-dir> ...]")
        return EXIT_NO_VERDICT

    exit_code = EXIT_CURRENT
    for argument in arguments:
        _out(argument)
        directory = Path(argument)
        tree = settle(name="lock", check=partial(check_tree, directory=directory))
        if tree.code == EXIT_NO_VERDICT:
            sources = Outcome(code=EXIT_CURRENT, lines=())
        else:
            sources = settle(name="source", check=partial(check_sources, directory=directory))
        code = worse(tree.code, sources.code)
        write = _out if code == EXIT_CURRENT else _err
        for line in (*tree.lines, *sources.lines):
            write(line)
        if code == EXIT_DRIFT:
            _err("  Run /pipelex-integrate to refresh the generated types.")
        exit_code = worse(exit_code, code)

    verdicts = {EXIT_CURRENT: "current", EXIT_DRIFT: "drift", EXIT_NO_VERDICT: "no verdict"}
    _out(f"\ncodegen-check: {verdicts[exit_code]}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
