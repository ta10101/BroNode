# BroNode (Holo Edge Node GUI) — release plan

Desktop helper for the **Holo Edge Node** container (`ghcr.io/holo-host/edgenode`). This file tracks packaging steps **1–4**.

| Step | Goal |
|------|------|
| **1** | App runs correctly from source on **Windows, macOS, Linux**; frozen build via **PyInstaller** on each OS; assets and paths correct. |
| **2** | Ship artifacts: **Windows** `.exe` + **MSI**; **Linux** tarball + install scripts; **macOS** `.app` / archive (+ optional DMG). |
| **3** | **README / install / uninstall** docs for each platform; Docker runtime cleanup documented separately from GUI uninstall. |
| **4** | **Branding** (wordmark), **GitHub Actions** release workflow, version tags, release notes. |

## Step 1 — checklist (redo / verify)

1. **Source run**
   - Windows: `python app.py`
   - macOS/Linux: `python3 app.py` (install `python3-tk`, Docker, optional `cairosvg` + libcairo2 on Linux)

2. **Smoke (no GUI)**  
   From the repository root:
   ```bash
   python packaging/smoke_step1.py
   ```

3. **Frozen build** (on each OS you support)
   ```bash
   python -m pip install -r requirements-build.txt
   python -m PyInstaller --noconfirm BroNode.spec
   ```
   - Windows: `dist/BroNode.exe`
   - Linux/macOS: `dist/BroNode`

4. **Optional debug logging** (file in system temp): set env `BRONODE_DEBUG_LOG=1` before launch.

When Step 1 is green on all targets, proceed to **Step 2**.

## Step 2 — installers & release artifacts

### Windows

| Output | How |
|--------|-----|
| `dist/BroNode.exe` | `.\build.ps1` |
| `dist/BroNodeSetup.msi` | `.\build.ps1 -Msi` (needs [WiX Toolset v3](https://wixtoolset.org/docs/wix3/) — `candle` / `light` on `PATH`) |

The MSI uses **WiX `WixUI_InstallDir`**: welcome → install folder (default is fine) → confirm → **progress** → finish, so non-technical users see what is happening. It installs to `Program Files\BroNode\BroNode.exe`. **Uninstall:** Settings → Apps → BroNode (Step 3 expands this).

The BroNode app shows a **one-time welcome dialog** on first launch (Docker + Start Here); see README → *Friendlier install*.

### Linux

| Output | How |
|--------|-----|
| `dist/BroNode` | `bash packaging/build_linux.sh` |
| `dist/bro-node-linux-x64-<version>.tar.gz` | `bash packaging/package_linux_tarball.sh` |

Extract the tarball, then from the inner folder: `chmod +x install.sh uninstall.sh BroNode && ./install.sh`  
**Uninstall:** `sudo ./uninstall.sh` (same folder, or copy script out first).

### macOS

| Output | How |
|--------|-----|
| `dist/BroNode.app` | `bash packaging/build_macos.sh` (on a Mac) |
| `dist/bro-node-macos-<version>.zip` | `bash packaging/package_macos_zip.sh` |

Open the `.app` or unzip and drag to **Applications**. For distribution outside the Mac App Store, **codesign** and ideally **notarize** (Apple Developer account).

### Version bumps

Keep **WiX** `Version` in `packaging/wix/BroNode.wxs`, **macOS** `CFBundleShortVersionString` / `CFBundleVersion` in `BroNode-macos.spec`, and **`APP_VERSION`** in `app.py` aligned when you cut a release.

When Step 2 artifacts exist, proceed to **Step 3** (full install/uninstall documentation).

## Step 3 — install / uninstall documentation (complete)

Canonical guide: **[docs/INSTALL_AND_UNINSTALL.md](docs/INSTALL_AND_UNINSTALL.md)**

It covers:

- **Two layers:** BroNode **GUI** vs **Edge Node Docker** (container `edgenode`, image, volume `holo-data`).
- **Windows:** MSI and portable exe install; **Settings → Apps** for MSI uninstall; `uninstall.ps1` and in-app **Uninstall Node Setup** for Docker only.
- **Linux:** tarball install / `uninstall.sh`; **`uninstall_docker_runtime.sh`** for Docker cleanup; paths and optional app data.
- **macOS:** `.app` install / Trash uninstall; same Docker commands or POSIX script.
- **Linux release tarball** now includes `INSTALL_AND_UNINSTALL.md`, `uninstall_docker_runtime.sh`, and install/uninstall scripts together.

README links to this doc from the top and from a short **Uninstall & Docker cleanup** table.

## Step 4 — branding & GitHub publish (complete)

| Item | Location |
|------|----------|
| **Wordmark** (phosphor green / void, matches UI) | [assets/bronode-wordmark.svg](assets/bronode-wordmark.svg) |
| **Release workflow** | [`.github/workflows/bronode-gui-release.yml`](../.github/workflows/bronode-gui-release.yml) |
| **How to tag & publish** | [RELEASING.md](RELEASING.md) |

**Tags:** push `bronode/v*` (e.g. `bronode/v1.0.0`) to trigger builds for Windows `.exe`, Linux `.tar.gz`, macOS `.zip` and create a **public GitHub Release** for this repository with those assets plus `INSTALL_AND_UNINSTALL.md`.

**MSI** is built locally (`.\build.ps1 -Msi`), not in CI — attach to the release by hand if you ship it.

Steps **1–4** for the BroNode GUI packaging track are complete; iterate versions via `APP_VERSION`, WiX, macOS plist, and `bronode/v*` tags together.
