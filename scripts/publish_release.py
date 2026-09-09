"""Publish or resume a release without moving tags or replacing existing assets."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from check_release import validate


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def get_release(repository, tag):
    # Fail closed on authentication/network errors. A successful listing without
    # this tag is the only condition under which we create a new draft.
    pages = json.loads(run("gh", "api", f"repos/{repository}/releases", "--paginate", "--slurp"))
    return next((release for page in pages for release in page
                 if release["tag_name"] == tag), None)


def publish(root, repository, sha):
    if os.environ.get("GITHUB_REF") != "refs/heads/master":
        raise ValueError("Releases can only be published from master")
    if run("git", "rev-parse", "HEAD") != sha:
        raise ValueError("Checkout does not match the commit that passed CI")
    remote = run("git", "ls-remote", "origin", "refs/heads/master").split()
    if not remote or remote[0] != sha:
        raise ValueError("master advanced; run the release workflow for its current commit")
    version, notes = validate(root)
    tag = f"release-{version}"
    tags = run("git", "tag", "--list", tag).splitlines()
    if tags:
        if run("git", "rev-parse", f"{tag}^{{commit}}") != sha:
            raise ValueError(f"{tag} already points to another commit; increase VERSION")
    else:
        run("git", "config", "user.name", "github-actions[bot]")
        run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        run("git", "tag", "-a", tag, "-m", f"nomo-pvad {version}", sha)
        run("git", "push", "origin", f"refs/tags/{tag}")

    release = get_release(repository, tag)
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        notes_path = temporary / "notes.md"
        notes_path.write_text(notes)
        if release is None:
            run("gh", "release", "create", tag, "--repo", repository, "--verify-tag",
                "--draft", "--title", f"nomo-pvad {version}", "--notes-file", str(notes_path))
            release = get_release(repository, tag)
            if release is None:
                raise RuntimeError("New draft release was not found")
        for name in ("nomo_pvad.pt", "CHECKSUMS.txt"):
            local = root / "weights" / name
            if not any(asset["name"] == name for asset in release["assets"]):
                run("gh", "release", "upload", tag, str(local), "--repo", repository)
            # Verify even assets left by a failed run. Never clobber mismatches.
            run("gh", "release", "download", tag, "--repo", repository,
                "--pattern", name, "--dir", str(temporary))
            expected = hashlib.sha256(local.read_bytes()).digest()
            if hashlib.sha256((temporary / name).read_bytes()).digest() != expected:
                raise ValueError(f"Existing release asset differs from the checked commit: {name}")
        if release["draft"]:
            run("gh", "release", "edit", tag, "--repo", repository, "--draft=false")
    print(f"Verified release and both assets: {tag} ({sha})")


if __name__ == "__main__":
    publish(Path(__file__).resolve().parents[1], os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"])
