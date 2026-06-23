#!/usr/bin/env python3
"""
_sync_third_party.py
====================
Downloads and caches third-party Kodi repository add-ons and plugins
as defined in sources/third-party-sources.yml.

Usage:
    python3 _sync_third_party.py [--dry-run]

Outputs:
    third-party/repos/   - Cached Kodi repository .zip files
    third-party/plugins/ - Cached individual plugin .zip files

Idempotent: skips downloads where the version file already exists.
"""

import argparse
import hashlib
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)

try:
    import json
except ImportError:
    pass  # json is stdlib, always available

# ─── Configuration ────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
SOURCES_FILE = ROOT / "sources" / "third-party-sources.yml"
REPOS_DIR = ROOT / "third-party" / "repos"
PLUGINS_DIR = ROOT / "third-party" / "plugins"
GITHUB_API = "https://api.github.com"

# Colour output
_COLORS = {
    "green": "\x1b[32m", "yellow": "\x1b[33m",
    "red": "\x1b[31m", "cyan": "\x1b[1;36m", "reset": "\x1b[0m"
}

def c(text, color):
    if sys.stdout.isatty():
        return f"{_COLORS.get(color,'')}{text}{_COLORS['reset']}"
    return text


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_sources():
    if not SOURCES_FILE.exists():
        print(c(f"[ERROR] Sources file not found: {SOURCES_FILE}", "red"))
        sys.exit(1)
    with open(SOURCES_FILE, "r") as f:
        return yaml.safe_load(f)


def download_file(url: str, dest: Path, dry_run: bool = False) -> bool:
    """Download a file from url to dest. Returns True if downloaded, False if skipped."""
    if dest.exists():
        print(c(f"  [SKIP] {dest.name} (already cached)", "yellow"))
        return False

    if dry_run:
        print(c(f"  [DRY ] Would download → {dest.name}", "cyan"))
        return True

    print(f"  [DOWN] {url}")
    print(f"       → {dest}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RPDevs-KodiSync/1.0"})
        with urllib.request.urlopen(req) as response, open(dest, "wb") as out:
            out.write(response.read())
        size = dest.stat().st_size
        print(c(f"  [OK  ] {dest.name} ({_human_size(size)})", "green"))
        return True
    except urllib.error.HTTPError as e:
        print(c(f"  [FAIL] HTTP {e.code}: {url}", "red"))
        return False
    except Exception as e:
        print(c(f"  [FAIL] {e}", "red"))
        return False


def _human_size(num: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"


def get_github_latest_release_asset(repo: str, pattern: str) -> tuple[str, str] | None:
    """
    Fetch the latest GitHub release for `repo` and return (asset_url, filename)
    for the first asset matching `pattern` (glob-style, * wildcard).
    """
    api_url = f"{GITHUB_API}/repos/{repo}/releases/latest"
    regex = re.compile(re.escape(pattern).replace(r"\*", ".*"))

    try:
        req = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "RPDevs-KodiSync/1.0",
            }
        )
        # Inject GH_TOKEN if available for higher rate limits
        gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if gh_token:
            req.add_header("Authorization", f"Bearer {gh_token}")

        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())

        for asset in data.get("assets", []):
            if regex.match(asset["name"]):
                return asset["browser_download_url"], asset["name"]

        print(c(f"  [WARN] No asset matching '{pattern}' in latest release of {repo}", "yellow"))
        return None
    except urllib.error.HTTPError as e:
        print(c(f"  [FAIL] GitHub API HTTP {e.code} for {repo}", "red"))
        return None
    except Exception as e:
        print(c(f"  [FAIL] GitHub API error: {e}", "red"))
        return None


def get_github_contents_latest_file(repo: str, path: str, pattern: str) -> tuple[str, str] | None:
    """
    Fetch directory listing from GitHub API for a repo path and return (download_url, filename)
    for the latest file matching the pattern.
    """
    api_url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    regex = re.compile(re.escape(pattern).replace(r"\*", ".*"))

    try:
        req = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "RPDevs-KodiSync/1.0",
            }
        )
        gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if gh_token:
            req.add_header("Authorization", f"Bearer {gh_token}")

        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())

        if not isinstance(data, list):
            print(c(f"  [FAIL] Expected a list of contents from {api_url}", "red"))
            return None

        matches = []
        for item in data:
            if item.get("type") == "file" and regex.match(item.get("name", "")):
                matches.append(item)

        if not matches:
            print(c(f"  [WARN] No files matching '{pattern}' in {repo}/{path}", "yellow"))
            return None

        # Sort matches by filename using natural sorting
        def version_key(item):
            filename = item["name"]
            return [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', filename)]

        matches.sort(key=version_key)
        latest_item = matches[-1]
        return latest_item["download_url"], latest_item["name"]

    except urllib.error.HTTPError as e:
        print(c(f"  [FAIL] GitHub API HTTP {e.code} for {repo}/{path}", "red"))
        return None
    except Exception as e:
        print(c(f"  [FAIL] GitHub API error: {e}", "red"))
        return None


# ─── Sync Functions ───────────────────────────────────────────────────────────

def sync_repos(entries: list, dry_run: bool) -> dict:
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    REPOS_DIR.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        name = entry.get("name", "unknown")
        url = entry.get("url", "")
        source_repo = entry.get("source_repo", "")
        path = entry.get("github_path", entry.get("path", ""))
        pattern = entry.get("pattern", entry.get("release_asset_pattern", ""))
        desc = entry.get("description", "")

        print(f"\n{c('→ REPO', 'cyan')} {name}")
        if desc:
            print(f"  {desc}")

        if not url and not (source_repo and path and pattern):
            print(c("  [FAIL] Missing url OR (source_repo + github_path + pattern)", "red"))
            stats["failed"] += 1
            continue

        if url:
            filename = url.split("/")[-1]
            dest = REPOS_DIR / filename
            dl_url = url
        else:
            print(f"  Fetching latest file matching '{pattern}' in {source_repo}/{path}...")
            result = get_github_contents_latest_file(source_repo, path, pattern)
            if result is None:
                stats["failed"] += 1
                continue
            dl_url, filename = result
            dest = REPOS_DIR / filename

        result = download_file(dl_url, dest, dry_run)
        if result:
            stats["downloaded"] += 1
        elif dest.exists():
            stats["skipped"] += 1
        else:
            stats["failed"] += 1

    return stats


def sync_plugins(entries: list, dry_run: bool) -> dict:
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        name = entry.get("name", "unknown")
        source_repo = entry.get("source_repo", "")
        path = entry.get("github_path", entry.get("path", ""))
        pattern = entry.get("release_asset_pattern", entry.get("pattern", ""))
        desc = entry.get("description", "")

        print(f"\n{c('→ PLUGIN', 'cyan')} {name}")
        if desc:
            print(f"  {desc}")

        if not source_repo or not pattern:
            print(c("  [FAIL] Missing source_repo or release_asset_pattern", "red"))
            stats["failed"] += 1
            continue

        if path:
            print(f"  Fetching latest file matching '{pattern}' in {source_repo}/{path}...")
            result = get_github_contents_latest_file(source_repo, path, pattern)
        else:
            print(f"  Fetching latest release from {source_repo}...")
            result = get_github_latest_release_asset(source_repo, pattern)

        if result is None:
            stats["failed"] += 1
            continue

        url, filename = result
        dest = PLUGINS_DIR / filename

        dl = download_file(url, dest, dry_run)
        if dl:
            stats["downloaded"] += 1
        elif dest.exists():
            stats["skipped"] += 1
        else:
            stats["failed"] += 1

    return stats


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sync third-party Kodi repos and plugins per sources/third-party-sources.yml"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without downloading")
    args = parser.parse_args()

    if args.dry_run:
        print(c("[DRY RUN MODE — no files will be downloaded]", "yellow"))

    sources = load_sources()
    repos = sources.get("repos", [])
    plugins = sources.get("plugins", [])

    total_stats = {"downloaded": 0, "skipped": 0, "failed": 0}

    # Sync repos
    if repos:
        print(f"\n{c('═══ SYNCING THIRD-PARTY REPOSITORIES ═══', 'cyan')}")
        stats = sync_repos(repos, args.dry_run)
        for k, v in stats.items():
            total_stats[k] += v
    else:
        print(c("\n[INFO] No third-party repos defined in sources file.", "yellow"))

    # Sync plugins
    if plugins:
        print(f"\n{c('═══ SYNCING THIRD-PARTY PLUGINS ═══', 'cyan')}")
        stats = sync_plugins(plugins, args.dry_run)
        for k, v in stats.items():
            total_stats[k] += v
    else:
        print(c("\n[INFO] No third-party plugins defined in sources file.", "yellow"))

    # Summary
    print(f"\n{c('═══ SYNC COMPLETE ═══', 'green')}")
    print(f"  Downloaded : {c(str(total_stats['downloaded']), 'green')}")
    print(f"  Skipped    : {c(str(total_stats['skipped']), 'yellow')}")
    print(f"  Failed     : {c(str(total_stats['failed']), 'red')}")

    if total_stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
