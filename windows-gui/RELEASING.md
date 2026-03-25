# Releasing BroNode (GUI)

GitHub Actions builds **Windows**, **Linux**, and **macOS** artifacts when you push a version tag.

## Where downloads appear

Releases are created on **whatever GitHub repository receives the tag** (your `git push origin <tag>` target).

- **This fork (`ta10101/BroNode`):** **[github.com/ta10101/BroNode/releases](https://github.com/ta10101/BroNode/releases)** — look for **BroNode GUI `bronode/v…`**.
- **Upstream after merge:** **[github.com/Holo-Host/edgenode/releases](https://github.com/Holo-Host/edgenode/releases)** (same tag pattern).
- Tags pushed to a **fork** create the release on that fork’s Releases page until commits exist on `Holo-Host/edgenode`.

**Repo settings (maintainers):** *Settings → Actions → General → Workflow permissions* should allow **Read and write** for `GITHUB_TOKEN` (needed to create the release and upload assets). The workflow sets `permissions: contents: write`.

## Tag format

Use tags under the `bronode/` prefix so they do not collide with other Edge Node releases:

```text
bronode/v1.0.0
bronode/v1.0.1
```

## Before you tag

1. Bump **`APP_VERSION`** in `windows-gui/app.py` (and keep **WiX** `Version` in `packaging/wix/BroNode.wxs` and **macOS** bundle versions in `BroNode-macos.spec` in sync — see [PACKAGING.md](PACKAGING.md)).
2. Commit and push to the default branch (e.g. `main`).
3. Create and push the tag:

```bash
git tag -a bronode/v1.0.0 -m "BroNode GUI 1.0.0"
git push origin bronode/v1.0.0
```

The workflow **bronode-gui-release** runs and attaches:

- `BroNode.exe` (Windows x64)
- `bro-node-linux-x64-<version>.tar.gz`
- `bro-node-macos-<version>.zip`

**MSI** (`BroNodeSetup.msi`) is not built in CI (WiX setup on runners is optional); build it locally with `.\build.ps1 -Msi` and attach manually if needed.

## Release notes

On GitHub: edit the generated release and summarize:

- Holo Edge Node image default: `ghcr.io/holo-host/edgenode`
- Link: [Install & uninstall](docs/INSTALL_AND_UNINSTALL.md)
- Docker required

## Manual workflow run (no release)

**Actions → bronode-gui-release → Run workflow** builds the three artifacts and uploads them as **workflow run artifacts** only. The **release** job is skipped unless the run is for a **tag**, so no GitHub Release is created from a plain dispatch.

## Branding

Wordmark for README / social: [assets/bronode-wordmark.svg](assets/bronode-wordmark.svg) (phosphor green on void background, matches the app chrome).
