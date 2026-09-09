"""Validate release metadata without importing inference dependencies."""
import argparse
import datetime
import hashlib
from pathlib import Path
import re
import subprocess


def version_tuple(value):
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value):
        raise ValueError("VERSION must contain X.Y with no leading zeros")
    return tuple(map(int, value.split(".")))


def release_notes(changelog, version):
    sections = list(re.finditer(r"^## (.+)$", changelog, re.MULTILINE))
    matches = [i for i, section in enumerate(sections)
               if re.fullmatch(rf"\[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}", section[1])]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one dated CHANGELOG section for {version}")
    i = matches[0]
    datetime.date.fromisoformat(sections[i][1].rsplit(" - ", 1)[1])
    end = sections[i + 1].start() if i + 1 < len(sections) else len(changelog)
    notes = changelog[sections[i].end():end].strip()
    notes = re.sub(r"^\[[^\]]+\]: .*\n?", "", notes, flags=re.MULTILINE).strip()
    if not notes:
        raise ValueError("Release notes must not be empty")
    return notes + "\n"


def validate(root, base_ref=None):
    version = (root / "VERSION").read_text().removesuffix("\n")
    current = version_tuple(version)
    notes = release_notes((root / "CHANGELOG.md").read_text(), version)
    for name, other in [("README.md", "README.zh-CN.md"), ("README.zh-CN.md", "README.md")]:
        readme = (root / name).read_text()
        if f"`{version}`" not in readme or f"`release-{version}`" not in readme:
            raise ValueError(f"{name} must identify version {version} and its release tag")
        if f"]({other})" not in readme:
            raise ValueError(f"{name} must link to {other}")
    lines = [line for line in (root / "weights/CHECKSUMS.txt").read_text().splitlines()
             if line.strip() and not line.startswith("#")]
    digest = hashlib.sha256((root / "weights/nomo_pvad.pt").read_bytes()).hexdigest()
    if lines != [f"{digest}  nomo_pvad.pt"]:
        raise ValueError("CHECKSUMS.txt does not match the bundled model weights")
    if base_ref:
        previous = subprocess.check_output(
            ["git", "show", f"{base_ref}:VERSION"], cwd=root, text=True).strip()
        if current <= version_tuple(previous):
            raise ValueError(f"Release PR must increase VERSION beyond {previous}")
        tags = subprocess.check_output(["git", "tag", "--list", "release-*"], cwd=root, text=True)
        for tag in tags.splitlines():
            if re.fullmatch(r"release-[0-9]+\.[0-9]+", tag):
                if current <= version_tuple(tag.removeprefix("release-")):
                    raise ValueError(f"Release PR version must be newer than {tag}")
        old_digest = subprocess.check_output(
            ["git", "show", f"{base_ref}:weights/CHECKSUMS.txt"], cwd=root, text=True)
        if old_digest != (root / "weights/CHECKSUMS.txt").read_text() and "### Model" not in notes:
            raise ValueError("Weight changes require a Model section in the release notes")
    return version, notes


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref")
    args = parser.parse_args()
    version, _ = validate(Path(__file__).resolve().parents[1], args.base_ref)
    print(f"Release metadata and weight checksum verified: {version}")
