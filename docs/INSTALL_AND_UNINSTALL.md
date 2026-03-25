# BroNode — install, uninstall, and Docker cleanup

BroNode is the **desktop control panel**. The **Holo Edge Node** is what runs **inside Docker** (container, image, and data volume). Removing one does not automatically remove the other.

| Layer | What it is | Typical names / paths |
|-------|------------|------------------------|
| **BroNode GUI** | Tkinter app you click | `BroNode.exe`, `BroNode.app`, `/opt/BroNode/BroNode` |
| **Edge Node (Docker)** | Holochain node in Docker | Container `edgenode`, image `ghcr.io/holo-host/edgenode`, volume `holo-data` |

**Uninstalling the GUI** frees disk space for the app only. **Your node data** stays in Docker until you remove the **container / image / volume** (or use BroNode’s **Uninstall Node Setup**).

---

## Windows

### Install

| Method | Steps |
|--------|--------|
| **MSI (recommended)** | Double-click `BroNodeSetup.msi`. Follow the wizard (folder, progress, finish). Start BroNode from the Start menu. |
| **Portable `.exe`** | Put `BroNode.exe` anywhere (e.g. Desktop). Double-click to run. No installer; you manage shortcuts yourself. |

You still need **Docker Desktop** installed and running: https://www.docker.com/products/docker-desktop/

### Uninstall — BroNode GUI only

| Method | Steps |
|--------|--------|
| **MSI install** | **Settings → Apps → Installed apps → BroNode → Uninstall.** |
| **Portable `.exe`** | Delete `BroNode.exe` and any shortcut you created. |

Optional: remove app data (resets first-run welcome, etc.): delete folder  
`%LOCALAPPDATA%\BroNode`  
(Press `Win+R`, paste `%LOCALAPPDATA%\BroNode`, Enter.)

### Remove — Edge Node Docker runtime only (DATA LOSS on volume)

This removes the **container**, **image**, and **`holo-data` volume** (persisted node data). It does **not** remove the BroNode app.

1. **Inside BroNode:** **Tools → Uninstall Node Setup** (confirm the dialog).  
   Uses the image/volume names shown in the Tools tab if you changed them.
2. **PowerShell script** (same defaults as above): from the BroNode repo root run  
   `.\uninstall.ps1`  
   Type `YES` when prompted.

Equivalent commands:

```powershell
docker rm -f edgenode
docker rmi ghcr.io/holo-host/edgenode
docker volume rm holo-data
```

If you use a **custom image name or volume**, change the commands (or use the in-app uninstall with your settings).

### Uninstall GUI and Docker cleanup

Do in either order. If you want **no leftover node data**, run **Uninstall Node Setup** (or `uninstall.ps1`) **before** or **after** removing the app — just remember volume removal is **irreversible** without a backup.

---

## Linux

### Install (from release tarball)

1. Extract: `tar -xzf bro-node-linux-x64-*.tar.gz`
2. `cd bro-node-linux-x64`
3. `chmod +x BroNode install.sh uninstall.sh`
4. `./install.sh`  
   Installs to `/opt/BroNode`, command `bronode`, and a `.desktop` menu entry.

Install **Docker Engine** separately for your distro: https://docs.docker.com/engine/install/

### Uninstall — BroNode GUI only

```bash
sudo ./uninstall.sh
```

(Default prefix `/opt/BroNode` — override with `PREFIX=/other/path sudo ./uninstall.sh` if you changed it at install time.)

Removes: `/opt/BroNode`, `/usr/local/bin/bronode`, menu shortcut. **Does not** touch Docker.

Optional app data: `rm -rf ~/.config/bronode`

### Remove — Edge Node Docker runtime only (DATA LOSS on volume)

**Option A — script** (from extracted tarball or repo):

```bash
bash packaging/linux/uninstall_docker_runtime.sh
```

**Option B — commands:**

```bash
docker rm -f edgenode
docker rmi ghcr.io/holo-host/edgenode
docker volume rm holo-data
```

Adjust names if you customized them in BroNode.

### Uninstall GUI and Docker cleanup

Run `./uninstall.sh` and `uninstall_docker_runtime.sh` in any order; understand volume removal deletes persisted data.

---

## macOS

### Install

1. Unzip `bro-node-macos-*.zip` if needed.
2. Drag **`BroNode.app`** to **Applications**.
3. Open it (first launch may require **System Settings → Privacy & Security** if the app is not signed).

Install **Docker Desktop for Mac** separately.

### Uninstall — BroNode GUI only

- Drag **`BroNode.app`** from **Applications** to **Trash**.
- Optional app data: delete folder  
  `~/Library/Application Support/BroNode`

### Remove — Edge Node Docker runtime only (DATA LOSS on volume)

In **Terminal**:

```bash
bash /path/to/BroNode/packaging/linux/uninstall_docker_runtime.sh
```

(or use the same three `docker` commands as in the Linux section).

### Uninstall GUI and Docker cleanup

Trash the `.app`, then run the Docker cleanup script or commands when you want node data gone.

---

## Source checkout (developers)

Run from the repository root:

```bash
python app.py    # or python3 app.py
```

No separate “uninstall” — use your venv/tools as usual. Docker cleanup is still the same `docker rm` / `volume rm` flow or **Tools → Uninstall Node Setup**.

---

## Quick reference

| Goal | Windows | Linux | macOS |
|------|---------|-------|--------|
| Remove **GUI** | Apps → Uninstall MSI, or delete `.exe` | `sudo ./uninstall.sh` | Trash `BroNode.app` |
| Remove **Edge Node in Docker** | Tools → Uninstall Node Setup or `uninstall.ps1` | `uninstall_docker_runtime.sh` or `docker` cmds | same `docker` cmds / script |
| **Backup data first** | Tools / **Data Backup** tab | same | same |

---

## Support files in this repo

| File | Role |
|------|------|
| `uninstall.ps1` | Windows: Docker runtime removal (not the MSI GUI) |
| `packaging/linux/uninstall.sh` | Linux: GUI removal |
| `packaging/linux/uninstall_docker_runtime.sh` | Linux/macOS: Docker runtime removal |
