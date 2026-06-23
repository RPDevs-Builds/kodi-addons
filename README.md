# RPDevs Kodi Add-on Repository

[![Build & Publish](https://github.com/RPDevs-Builds/kodi-addons/actions/workflows/build-repo.yml/badge.svg)](https://github.com/RPDevs-Builds/kodi-addons/actions/workflows/build-repo.yml)
[![Sync Third-Party](https://github.com/RPDevs-Builds/kodi-addons/actions/workflows/sync-third-party.yml/badge.svg)](https://github.com/RPDevs-Builds/kodi-addons/actions/workflows/sync-third-party.yml)

The official Kodi add-on repository for **RPDevs-Builds**. Hosts first-party scrapers and plugins, plus curated third-party add-ons.

---

## 🎯 Install in Kodi

**Method 1 — File Manager Source (recommended)**

Add this URL as a file manager source in Kodi:
```
https://rpdevs-builds.github.io/kodi-addons/
```
Then install `repository.rpdevs-*.zip` from that source.

**Method 2 — Direct ZIP Install**

Download the installer zip from this page and install via:  
`Settings → Add-ons → Install from zip file`

---

## 📦 Repository Contents

### First-Party Add-ons
| Add-on | Description | Source |
| :--- | :--- | :--- |
| `metadata.anime.otaku.python` | Anime metadata scraper (AniList, AniZip, TVDB, TMDb) | [RPDevs-Builds/metadata.anime.otaku.python](https://github.com/RPDevs-Builds/metadata.anime.otaku.python) |

### Third-Party Add-ons
Sourced from `sources/third-party-sources.yml` and synced weekly.

---

## 🏗️ Repository Architecture

```
kodi-addons/
├── .github/workflows/
│   ├── build-repo.yml          # Builds zips + addons.xml → deploys to Pages
│   ├── sync-third-party.yml    # Weekly sync of third-party sources
│   └── import-releases.yml    # Triggered by addon release CIs
├── repo/                       # Universal add-on sources (all Kodi versions)
│   ├── repository.rpdevs/      # The repo add-on itself
│   └── metadata.anime.otaku.python/  # Git submodule (first-party)
├── sources/
│   └── third-party-sources.yml # Declarative third-party sync manifest
├── third-party/
│   ├── repos/                  # Cached third-party Kodi repo zips
│   └── plugins/                # Cached third-party plugin zips
├── _repo_generator.py          # Generates addons.xml + zips from /repo
└── _sync_third_party.py        # Downloads third-party sources
```

---

## 🔧 Local Development

**Prerequisites:** Python 3.10+, `pyyaml`

```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/RPDevs-Builds/kodi-addons.git
cd kodi-addons

# Install Python deps
pip install pyyaml

# Build the repository locally
python3 _repo_generator.py

# Sync third-party add-ons (dry run)
python3 _sync_third_party.py --dry-run

# Sync for real
python3 _sync_third_party.py
```

---

## ➕ Adding a New First-Party Add-on

```bash
# 1. Add as submodule
git submodule add https://github.com/RPDevs-Builds/your-addon.git repo/your-addon

# 2. Pin to a release tag
cd repo/your-addon && git checkout v1.0.0 && cd ../..

# 3. Commit
git add .gitmodules repo/your-addon
git commit -m "feat: add your-addon v1.0.0"
git push
```

The `build-repo.yml` workflow will automatically pick it up.

---

## ➕ Adding a New Third-Party Source

Edit [`sources/third-party-sources.yml`](sources/third-party-sources.yml) and add an entry under `repos:` or `plugins:`.  
The next weekly sync (or a manual `workflow_dispatch`) will download it.

---

## 🔗 Cross-Repo Automation

To have another repo automatically update its submodule pointer here on release, add this to its release workflow:

```yaml
- name: Notify kodi-addons repository
  run: |
    curl -X POST https://api.github.com/repos/RPDevs-Builds/kodi-addons/dispatches \
      -H "Authorization: Bearer ${{ secrets.KODI_ADDONS_DISPATCH_TOKEN }}" \
      -H "Accept: application/vnd.github+json" \
      -d '{"event_type":"addon-released","client_payload":{"addon":"your-addon-name","version":"${{ github.ref_name }}"}}'
```

> **Required secret:** `KODI_ADDONS_DISPATCH_TOKEN` — a PAT with `repo` scope on `RPDevs-Builds/kodi-addons`.
