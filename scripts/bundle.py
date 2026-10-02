#!/usr/bin/env python3
"""Build an offline package bundle from a requirements list.

Reads requirements from the REQUIREMENTS env var (or --requirements-file),
downloads every package plus all of its dependencies as wheels for the current
interpreter/platform, verifies that an offline install resolves with
--no-index, and writes a pinned requirements.txt next to the wheels.

Output layout (inside --out):
    packages/                 all .whl files
    requirements.txt          pinned list of everything in packages/
    requirements.input.txt    the requirements exactly as requested
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import platform
import subprocess
import sys

# Options that take a value, so "-i URL" stays on one line when splitting a
# single-line input such as the one typed into GitHub's "Run workflow" form.
OPTIONS_WITH_ARG = {
    "-i", "--index-url", "--extra-index-url", "-f", "--find-links",
    "--trusted-host", "-c", "--constraint", "-r", "--requirement",
    "--no-binary", "--only-binary",
}
OPERATOR_CHARS = tuple("=<>!~;@,[(")


def normalize(raw: str) -> list[str]:
    """Turn pasted text into requirement lines.

    Multi-line input is used as-is. A single line holding several
    space-separated requirements (e.g. "requests flask>=3 numpy") is split,
    keeping version specifiers, markers and option values attached.
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text.strip() and "\\n" in text:
        text = text.replace("\\n", "\n")

    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line and not line.startswith("#")]
    if len(lines) != 1:
        return lines

    merged: list[str] = []
    for token in lines[0].split():
        if merged and (
            token.startswith(OPERATOR_CHARS)
            or merged[-1].endswith(OPERATOR_CHARS)
            or merged[-1] in OPTIONS_WITH_ARG
        ):
            merged[-1] = f"{merged[-1]} {token}"
        else:
            merged.append(token)
    return merged


def pip(*args: str) -> None:
    cmd = [sys.executable, "-m", "pip", *args, "--progress-bar", "off", "--disable-pip-version-check"]
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def wheel_name_version(path: pathlib.Path) -> tuple[str, str]:
    # {name}-{version}(-{build})?-{python}-{abi}-{platform}.whl
    name, version = path.stem.split("-")[:2]
    return name.replace("_", "-").lower(), version


def summary(text: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main() -> int:
    # Windows consoles/pipes may default to cp1252, which can't encode the emoji below.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--requirements-file", help="read requirements from this file instead of $REQUIREMENTS")
    parser.add_argument("--mode", choices=["wheels-only", "build-sdists"], default="wheels-only")
    parser.add_argument("--target", default=f"{platform.system().lower()}-{platform.machine().lower()}")
    parser.add_argument("--out", default="bundle")
    args = parser.parse_args()

    raw = pathlib.Path(args.requirements_file).read_text() if args.requirements_file else os.environ.get("REQUIREMENTS", "")
    lines = normalize(raw)
    if not lines:
        print("❌ No requirements given.", file=sys.stderr)
        return 1

    out = pathlib.Path(args.out)
    packages = out / "packages"
    packages.mkdir(parents=True, exist_ok=True)
    input_file = out / "requirements.input.txt"
    input_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"=== Requirements ({len(lines)} lines) — Python {py}, {args.target}, {args.mode} ===")
    print(input_file.read_text())

    # ── Download ────────────────────────────────────────────────────────────
    try:
        if args.mode == "wheels-only":
            pip("download", "-r", str(input_file), "--only-binary=:all:", "-d", str(packages))
        else:
            # Downloads wheels where available and builds the rest from sdist
            # on this runner, so the bundle still contains only wheels.
            pip("wheel", "-r", str(input_file), "--prefer-binary", "-w", str(packages))
    except subprocess.CalledProcessError:
        summary("## ❌ Download failed\n")
        if args.mode == "wheels-only":
            summary("Some package probably has no wheel for this Python/OS. "
                    "Try mode `build-sdists` or another Python version.")
        return 1

    # ── Verify: offline dry-run must resolve everything ─────────────────────
    try:
        pip("install", "--no-index", "--find-links", str(packages), "--dry-run",
            "--ignore-installed", "-r", str(input_file))
    except subprocess.CalledProcessError:
        summary("## ❌ Offline verification failed\n\n`pip install --no-index` could not resolve all packages.")
        return 1
    print("✅ All dependencies satisfied offline")

    # ── Pinned requirements.txt ─────────────────────────────────────────────
    wheels = sorted(packages.glob("*.whl"))
    pinned = sorted({"{}=={}".format(*wheel_name_version(w)) for w in wheels})
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    header = [
        "# ============================================================",
        "# Python Offline Install — Requirements",
        f"# Python   : {py}",
        f"# OS       : {args.target}",
        f"# Mode     : {args.mode}",
        f"# Generated: {generated}",
        "# Usage    : pip install --no-index --find-links=packages -r requirements.txt",
        "# ============================================================",
        "",
    ]
    (out / "requirements.txt").write_text("\n".join(header + pinned) + "\n", encoding="utf-8")

    print("\n=== Downloaded packages ===")
    for w in wheels:
        print(f"  {w.name}")

    size_mb = sum(w.stat().st_size for w in wheels) / 1024 / 1024
    summary("\n".join([
        "## ✅ Download Complete",
        "",
        "| Key | Value |",
        "|-----|-------|",
        f"| Python | `{py}` |",
        f"| Target OS | `{args.target}` |",
        f"| Mode | `{args.mode}` |",
        f"| Packages | {len(wheels)} .whl files ({size_mb:.1f} MB) |",
        "",
        "**Install command:**",
        "```",
        "pip install --no-index --find-links=packages -r requirements.txt",
        "```",
        "",
        "<details><summary>Pinned requirements</summary>",
        "",
        "```",
        *pinned,
        "```",
        "</details>",
    ]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
