import datetime
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import webbrowser
import shlex
import tkinter as tk
from tkinter import filedialog, ttk


def _resource_root():
    """Directory containing bundled assets (app folder in dev, _MEIPASS when frozen)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _debug_log_file_path():
    """NDJSON debug log only if BRONODE_DEBUG_LOG=1 (cross-platform temp dir)."""
    v = (os.environ.get("BRONODE_DEBUG_LOG") or "").strip().lower()
    if v not in ("1", "true", "yes", "on"):
        return None
    return os.path.join(tempfile.gettempdir(), "bronode-debug.ndjson")


def _default_happ_config_tool_path():
    """Sibling repo path to happ_config_file (dev only); empty when frozen or missing."""
    if _is_frozen():
        return ""
    gui_dir = os.path.dirname(os.path.abspath(__file__))
    base = os.path.normpath(os.path.join(gui_dir, "tools", "happ_config_file", "target", "release"))
    name = "happ_config_file.exe" if sys.platform == "win32" else "happ_config_file"
    p = os.path.join(base, name)
    return p if os.path.isfile(p) else ""


APP_NAME = "BroNode"
APP_VERSION = "1.0.2"
# Visual system: deep void + phosphor readout (lightweight, no literal theme labels in UI)
UI_BG = "#030a07"
UI_SURFACE = "#0c1812"
UI_RISE = "#102218"
UI_DEEP = "#060f0c"
UI_INPUT_BG = "#0f1e18"
UI_BORDER = "#2d5240"
UI_BORDER_STRONG = "#3d6b52"
UI_BORDER_FOCUS = "#4ade80"
UI_GRID = "#0f2218"
UI_ACCENT = "#00e676"
UI_ACCENT_DIM = "#34d399"
UI_TEXT = "#e8f5ec"
UI_TEXT_MUTE = "#8fb3a0"
UI_WARN = "#fbbf24"
UI_ERR = "#f87171"
if sys.platform == "win32":
    FONT_MONO = ("Cascadia Mono", 9)
    FONT_MONO_SM = ("Cascadia Mono", 8)
elif sys.platform == "darwin":
    FONT_MONO = ("Menlo", 9)
    FONT_MONO_SM = ("Menlo", 8)
else:
    FONT_MONO = ("DejaVu Sans Mono", 9)
    FONT_MONO_SM = ("DejaVu Sans Mono", 8)
CONTAINER_NAME = "edgenode"
# holochain conductor + hc run as nonroot; docker exec defaults to root and cannot talk to the admin API.
CONTAINER_USER = "nonroot"
DEFAULT_IMAGE = "ghcr.io/holo-host/edgenode"
DEFAULT_VOLUME = "holo-data"
MASCOT_SVG = os.path.join(_resource_root(), "assets", "holobro-mascot.svg")
APP_CATALOG = [
    {
        "label": "Kando (example release)",
        "name": "kando",
        "version": "0.17.1",
        "happ_url": "https://github.com/holochain-apps/kando/releases/download/v0.17.1/kando.happ",
        "notes": "Task/project example preset for installing apps on this node.",
    },
    {
        "label": "Forum DNA (example placeholder)",
        "name": "forum",
        "version": "0.1.0",
        "happ_url": "https://example.com/forum.happ",
        "notes": "Placeholder preset. Replace URL with your app release artifact.",
    },
    {
        "label": "Custom (manual)",
        "name": "my_happ",
        "version": "0.1.0",
        "happ_url": "https://example.com/my_app.happ",
        "notes": "Start here for your own hApp release URL.",
    },
]


def _windows_docker_cli_exe():
    """Use docker.exe next to a .cmd/.bat shim so Windows does not spawn a visible cmd.exe host."""
    p = shutil.which("docker")
    if not p:
        return None
    low = p.lower()
    if low.endswith(".exe") and os.path.isfile(p):
        return p
    if low.endswith((".cmd", ".bat")):
        d = os.path.dirname(p)
        exe = os.path.join(d, "docker.exe")
        if os.path.isfile(exe):
            return exe
    stem, ext = os.path.splitext(p)
    if ext.lower() not in (".exe", ".cmd", ".bat"):
        exe = stem + ".exe"
        if os.path.isfile(exe):
            return exe
    return p


def _normalize_subprocess_argv(command):
    """Windows: rewrite docker launcher to real docker.exe when possible (avoids console flashes)."""
    cmd = list(command)
    if sys.platform != "win32" or len(cmd) < 1:
        return cmd
    base = os.path.basename(cmd[0]).lower()
    if base in ("docker", "docker.cmd", "docker.bat"):
        resolved = _windows_docker_cli_exe()
        if resolved:
            cmd[0] = resolved
    return cmd


def _subprocess_no_console_kwargs():
    """Windows: hide console for child processes so the GUI does not flash cmd/conhost windows."""
    if sys.platform != "win32":
        return {}
    kwargs = {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if flags:
        kwargs["creationflags"] = flags
    # CREATE_NO_WINDOW alone is sometimes not enough for shims; STARTUPINFO hides the initial window.
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = si
    except (AttributeError, OSError):
        pass
    return kwargs


def run_command(command, timeout=20):
    command = _normalize_subprocess_argv(command)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=False,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            **_subprocess_no_console_kwargs(),
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return (
            127,
            "",
            "Command not found. Install Docker and ensure `docker` is on your PATH (Docker Desktop on Windows/macOS, or Docker Engine on Linux).",
        )
    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out."


def is_missing_container_error(text):
    if not text:
        return False
    lowered = text.lower()
    return "no such container" in lowered or "not found" in lowered


def is_docker_daemon_error(text):
    if not text:
        return False
    t = text.lower()
    return (
        "npipe" in t
        or "dockerdesktoplinuxengine" in t
        or ("docker api" in t and ("failed" in t or "error" in t))
        or "cannot find the file specified" in t
        or "the system cannot find the file" in t
        or "connection refused" in t
        or "is the docker daemon running" in t
    )


def format_docker_user_message(raw):
    """Turn raw docker stderr into a short, actionable message on Windows/macOS/Linux."""
    if not raw:
        return "Docker command failed."
    if is_docker_daemon_error(raw):
        return (
            "Docker Desktop is not running or the engine is not ready yet.\n\n"
            "What to do:\n"
            "1) Open Docker Desktop from the Start menu\n"
            "2) Wait until it shows the engine is running (whale icon idle)\n"
            "3) Retry your action\n\n"
            f"Details:\n{raw.strip()[:600]}"
        )
    return raw.strip()


def strip_ansi(text):
    if not text:
        return ""
    return re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", text)


def get_local_ipv4():
    """IPv4 used for typical outbound traffic (UDP trick); not necessarily your only interface."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.8)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "unknown"


def vpn_adapter_hint_windows():
    """Heuristic: look for VPN/tunnel-style adapter names in `ipconfig` (Windows)."""
    code, out, _ = run_command(["ipconfig"], timeout=12)
    if code != 0 or not out:
        return "could not read ipconfig", []
    hits = []
    for line in out.splitlines():
        line = line.strip()
        if not line.endswith(":"):
            continue
        if "adapter" not in line.lower():
            continue
        name = line.split(":", 1)[0].strip()
        low = name.lower()
        markers = (
            "vpn",
            "wireguard",
            "wintun",
            "tap-windows",
            "tap ",
            " tun",
            "openvpn",
            "zerotier",
            "tailscale",
            "nordlynx",
            "cisco",
            "anyconnect",
            "ppp",
            "pptp",
            "l2tp",
            "ipsec",
            "checkpoint",
            "fortinet",
            "globalprotect",
            "pangp",
            "wg ",
            "nebula",
            "hamachi",
        )
        if any(m in low for m in markers):
            hits.append(name)
    if hits:
        return "tunnel / VPN-style adapter seen", hits[:10]
    return "no VPN-style adapter name in ipconfig", []


def vpn_adapter_hint_unix():
    """Heuristic on Linux/macOS: `ip -br link`, then `ifconfig` for utun/tun."""
    hits = []
    code, out, _ = run_command(["ip", "-br", "link"], timeout=8)
    if code == 0 and out:
        markers = (
            "wg", "tun", "tap", "zt", "vpn", "tailscale", "zerotier", "ppp", "ipsec",
            "gtun", "nebula", "hamachi", "outline", "cloudflared",
        )
        for line in out.splitlines():
            parts = line.split()
            if not parts:
                continue
            ifname = parts[0].split("@")[0]
            low = ifname.lower()
            if any(m in low for m in markers):
                hits.append(ifname)
    if hits:
        return "tunnel / VPN-style iface (ip link)", hits[:10]

    code2, out2, _ = run_command(["ifconfig"], timeout=12)
    if code2 == 0 and out2:
        for line in out2.splitlines():
            line = line.strip()
            if not line or line[0] in ("\t", " "):
                continue
            if ":" in line:
                name = line.split(":", 1)[0].strip()
                low = name.lower()
                if name.startswith("utun") or name.startswith("tun") or name.startswith("tap") or "ppp" in low:
                    hits.append(name)
        if hits:
            return "possible tunnel iface (ifconfig)", hits[:10]

    return "no obvious VPN/tun iface (ip / ifconfig)", []


def vpn_adapter_hint():
    if sys.platform == "win32":
        return vpn_adapter_hint_windows()
    return vpn_adapter_hint_unix()


def docker_exec_base():
    return ["docker", "exec", "-u", CONTAINER_USER, "-i", CONTAINER_NAME]


def parse_list_apps_json(text):
    """Parse `hc list-apps` JSON from stdout that may include log lines or wrappers."""
    if not text:
        return None
    t = strip_ansi(text.strip())
    lines = []
    for line in t.splitlines():
        low = line.strip().lower()
        if low.startswith("initialising") or low.startswith("initializing"):
            continue
        lines.append(line)
    t = "\n".join(lines).strip()

    def try_parse(s):
        try:
            return json.loads(s)
        except Exception:
            return None

    data = try_parse(t)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("result", "data", "apps"):
            v = data.get(key)
            if isinstance(v, list):
                return v

    i = t.find("[")
    if i >= 0:
        depth = 0
        for j in range(i, len(t)):
            c = t[j]
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    data = try_parse(t[i : j + 1])
                    if isinstance(data, list):
                        return data
                    break
    return None


def extract_dna_hash_from_app(app):
    """First provisioned cell DNA hash from list-apps JSON object."""
    if not isinstance(app, dict):
        return None
    ci = app.get("cell_info") or {}
    for _role, cell_list in ci.items():
        if not isinstance(cell_list, list):
            continue
        for cell in cell_list:
            if not isinstance(cell, dict):
                continue
            val = cell.get("value") or {}
            cid = val.get("cell_id") or {}
            dna = cid.get("dna_hash")
            if dna:
                return str(dna)
    return None


def parse_hc_json_object(text):
    """Parse a single JSON object from `hc s call` output (may strip log lines)."""
    if not text:
        return None
    t = strip_ansi(text.strip())
    lines = []
    for line in t.splitlines():
        low = line.strip().lower()
        if low.startswith("initialising") or low.startswith("initializing"):
            continue
        lines.append(line)
    t = "\n".join(lines).strip()
    try:
        data = json.loads(t)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    i = t.find("{")
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(t)):
        c = t[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(t[i : j + 1])
                    return data if isinstance(data, dict) else None
                except Exception:
                    return None
    return None

class EdgeNodeGui:
    def __init__(self, root):
        self.root = root
        self._debug_log_path = _debug_log_file_path()
        self._debug_run_id = "main"
        self.root.title(f"{APP_NAME} — edge node manager")
        self.root.geometry("1180x780")
        self.root.minsize(980, 620)
        self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)
        self.root.report_callback_exception = self._tk_callback_exception

        self.status_vars = {
            "Local IP": tk.StringVar(value="-"),
            "Docker": tk.StringVar(value="-"),
            "Container": tk.StringVar(value="-"),
            "Running": tk.StringVar(value="-"),
            "Status": tk.StringVar(value="-"),
            "Image": tk.StringVar(value="-"),
            "StartedAt": tk.StringVar(value="-"),
        }

        self.stats_vars = {
            "CPU": tk.StringVar(value="-"),
            "Memory": tk.StringVar(value="-"),
            "NetIO": tk.StringVar(value="-"),
            "BlockIO": tk.StringVar(value="-"),
            "PIDs": tk.StringVar(value="-"),
        }

        self.logs_text = None
        self.image_var = tk.StringVar(value=DEFAULT_IMAGE)
        self.volume_var = tk.StringVar(value=DEFAULT_VOLUME)
        self.config_tool_path_var = tk.StringVar(value=_default_happ_config_tool_path())
        self.config_input_var = tk.StringVar(value="")
        self.config_name_var = tk.StringVar(value="my_happ")
        self.config_iroh_var = tk.BooleanVar(value=True)
        self.config_gateway_var = tk.BooleanVar(value=False)
        self.config_economics_var = tk.BooleanVar(value=False)
        self.config_init_zome_var = tk.BooleanVar(value=False)
        self.install_config_var = tk.StringVar(value="")
        self.node_name_var = tk.StringVar(value="")
        self.app_id_var = tk.StringVar(value="")
        self.admin_port_var = tk.StringVar(value="4444")
        self.ops_output_text = None
        self.apps_tree = None
        self.catalog_tree = None
        self._catalog_syncing = False
        self.apps_count_var = tk.StringVar(value="Installed apps: 0")
        self.apps_enabled_var = tk.StringVar(value="Enabled: 0")
        self.apps_last_var = tk.StringVar(value="Latest app: -")
        self.backup_dir_var = tk.StringVar(value="")
        self.restore_file_var = tk.StringVar(value="")
        self.catalog_choice_var = tk.StringVar(value=APP_CATALOG[0]["label"])
        self.catalog_name_var = tk.StringVar(value=APP_CATALOG[0]["name"])
        self.catalog_version_var = tk.StringVar(value=APP_CATALOG[0]["version"])
        self.catalog_url_var = tk.StringVar(value=APP_CATALOG[0]["happ_url"])
        self.catalog_seed_var = tk.StringVar(value="")
        self.catalog_info_var = tk.StringVar(value=APP_CATALOG[0]["notes"])
        self.show_raw_output_var = tk.BooleanVar(value=False)

        self.cpu_history = []
        self.mem_history = []
        self.history_max_points = 60
        self.chart_canvas = None
        self.auto_refresh_job = None
        self.dep_canvas = None
        self.dep_status_var = tk.StringVar(value="Checking dependencies...")
        self.dep_action_var = tk.StringVar(value="Resolving...")
        self.action_status_var = tk.StringVar(value="Idle")
        self.dependencies_ready = False
        self.bootstrap_complete = False
        self.dep_action_button = None
        self.banner_text = ""
        self.banner_canvas = None
        self.banner_item = None
        self.banner_x = 0
        self.banner_last_text = ""
        self.banner_speed_var = tk.IntVar(value=50)
        self.tab_frames = {}
        self.nav_row_frames = {}
        self.current_tab_name = "Start Here"
        self.hosting_title_var = tk.StringVar(value="Apps: 0")
        self.hosting_text = None
        self.hosted_apps_cache = []
        self.hosted_apps_list_cache = []
        self.last_hosted_refresh_ms = 0
        self._setup_theme()
        self._build_ui()
        self.start_banner_loop()
        self.root.after(200, self.ensure_dependencies_and_continue)
        self.root.after(120, self.refresh_network)
        self.root.after(650, self._maybe_show_first_run_welcome)

    def _user_data_dir(self):
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            d = os.path.join(base, "BroNode")
        elif sys.platform == "darwin":
            d = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "BroNode")
        else:
            d = os.path.join(os.path.expanduser("~"), ".config", "bronode")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        return d

    def _maybe_show_first_run_welcome(self):
        """One-time friendly explanation for non-technical users (after OK, not shown again)."""
        if (os.environ.get("BRONODE_SKIP_WELCOME") or "").strip().lower() in ("1", "true", "yes"):
            return
        sentinel = os.path.join(self._user_data_dir(), "welcome_ok_v1")
        if os.path.isfile(sentinel):
            return
        self.ui_info(
            "Welcome to BroNode",
            "BroNode is a simple control panel for the Holo Edge Node — a Holochain node that runs "
            "inside Docker on your computer.\n\n"
            "What to expect:\n"
            "• The Start Here tab walks you through: pull the node image, start the container, "
            "then pick apps.\n"
            "• Docker must be installed and running before BroNode can do its job.\n"
            "  If you need Docker: https://www.docker.com/products/docker-desktop/\n\n"
            "You can always open Start Here again from the top buttons.\n\n"
            "Click OK to continue.",
        )
        try:
            with open(sentinel, "w", encoding="utf-8") as f:
                f.write("1\n")
        except OSError:
            pass

    def _debug_log(self, kind, location, message, data=None, run_id=None):
        if not self._debug_log_path:
            return
        payload = {
            "sessionId": "bronode",
            "runId": run_id or self._debug_run_id,
            "kind": kind,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(datetime.datetime.now().timestamp() * 1000),
        }
        try:
            with open(self._debug_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _tk_callback_exception(self, exc, val, tb):
        self._debug_log(
            "error",
            "app.py:_tk_callback_exception",
            "Unhandled Tk callback exception",
            {"exc_type": getattr(exc, "__name__", str(exc)), "error": str(val)},
        )
        import traceback

        traceback.print_exception(exc, val, tb)

    def _setup_theme(self):
        self.root.configure(bg=UI_BG)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", background=UI_BG, foreground=UI_TEXT)
        style.configure("TFrame", background=UI_BG)
        style.configure("TLabel", background=UI_BG, foreground=UI_TEXT, font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI Semibold", 20), foreground=UI_ACCENT_DIM)
        style.configure("Subtle.TLabel", foreground=UI_TEXT_MUTE, font=("Segoe UI", 10))
        style.configure(
            "Field.TLabel",
            background=UI_BG,
            foreground=UI_TEXT,
            font=("Segoe UI Semibold", 9),
        )
        style.configure("Graffiti.TLabel", font=("Segoe UI Black", 26), foreground=UI_ACCENT)
        style.configure("Tag.TLabel", foreground=UI_TEXT_MUTE, font=FONT_MONO_SM)
        style.configure(
            "TButton",
            background=UI_RISE,
            foreground=UI_ACCENT_DIM,
            borderwidth=1,
            relief="flat",
            focusthickness=0,
            focuscolor=UI_BORDER,
            padding=(12, 8),
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "TButton",
            background=[("active", "#163d28"), ("pressed", "#0f2a1c")],
            foreground=[("active", UI_TEXT), ("pressed", UI_ACCENT)],
        )
        style.configure(
            "Secondary.TButton",
            background=UI_DEEP,
            foreground=UI_TEXT_MUTE,
            borderwidth=1,
            relief="flat",
            padding=(10, 8),
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", UI_RISE)],
            foreground=[("active", UI_TEXT)],
        )
        style.configure("TNotebook", background=UI_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=UI_SURFACE, foreground=UI_TEXT_MUTE, padding=(12, 8))
        style.map("TNotebook.Tab", background=[("selected", UI_RISE)], foreground=[("selected", UI_ACCENT_DIM)])
        style.configure("Nav.TFrame", background=UI_SURFACE)
        style.configure(
            "TEntry",
            fieldbackground=UI_INPUT_BG,
            foreground=UI_TEXT,
            insertcolor=UI_ACCENT,
            borderwidth=1,
            relief="flat",
        )
        style.map(
            "TEntry",
            fieldbackground=[("readonly", UI_INPUT_BG), ("disabled", UI_DEEP)],
            lightcolor=[("focus", UI_BORDER_FOCUS), ("!focus", UI_BORDER_STRONG)],
            darkcolor=[("focus", UI_BORDER_FOCUS), ("!focus", UI_BORDER_STRONG)],
        )
        style.configure(
            "Card.TLabelframe",
            background=UI_BG,
            relief="solid",
            borderwidth=1,
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=UI_BG,
            foreground=UI_ACCENT_DIM,
            font=("Segoe UI Semibold", 10),
        )
        style.configure("TCheckbutton", background=UI_BG, foreground=UI_TEXT_MUTE)
        style.map("TCheckbutton", background=[("active", UI_BG)], foreground=[("active", UI_TEXT)])
        style.configure(
            "Treeview",
            background=UI_INPUT_BG,
            fieldbackground=UI_INPUT_BG,
            foreground=UI_TEXT,
            rowheight=28,
            font=FONT_MONO_SM,
        )
        style.configure("Treeview.Heading", background=UI_RISE, foreground=UI_ACCENT_DIM, font=("Segoe UI Semibold", 9))
        style.map("Treeview", background=[("selected", "#143d28")], foreground=[("selected", UI_TEXT)])
        style.configure("TSeparator", background=UI_BORDER)
        style.configure("TCombobox", fieldbackground=UI_INPUT_BG, foreground=UI_TEXT, borderwidth=1)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", UI_INPUT_BG)],
            lightcolor=[("focus", UI_BORDER_FOCUS), ("!focus", UI_BORDER_STRONG)],
            darkcolor=[("focus", UI_BORDER_FOCUS), ("!focus", UI_BORDER_STRONG)],
        )

    def _build_ui(self):
        hero = ttk.Frame(self.root)
        hero.pack(fill=tk.X, padx=16, pady=(16, 4))
        ttk.Label(hero, text="BRO//NODE", style="Graffiti.TLabel").pack(side=tk.LEFT, anchor="w")
        ttk.Label(
            hero,
            text="Simple edge-node control panel",
            style="Subtle.TLabel",
        ).pack(side=tk.LEFT, padx=14, pady=(8, 0))
        self._build_dependency_widget(hero)
        ttk.Label(hero, textvariable=self.action_status_var, style="Tag.TLabel").pack(
            side=tk.RIGHT, padx=(0, 10), pady=(8, 0)
        )

        banner_outer = tk.Frame(self.root, bg=UI_BG)
        banner_outer.pack(fill=tk.X, padx=14, pady=(0, 6))

        banner_frame = tk.Frame(banner_outer, bg=UI_BG, highlightthickness=1, highlightbackground=UI_BORDER_STRONG)
        banner_frame.pack(fill=tk.BOTH, expand=True)
        self.banner_canvas = tk.Canvas(
            banner_frame,
            bg=UI_DEEP,
            height=28,
            highlightthickness=0,
            bd=0,
            relief=tk.FLAT,
        )
        self.banner_canvas.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        self.banner_canvas.bind("<Configure>", self._on_banner_resize)
        speed_row = tk.Frame(banner_outer, bg=UI_BG)
        speed_row.pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Label(speed_row, text="Banner scroll", style="Tag.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(speed_row, text="slow", style="Tag.TLabel").pack(side=tk.LEFT)
        tk.Scale(
            speed_row,
            variable=self.banner_speed_var,
            from_=1,
            to=100,
            orient=tk.HORIZONTAL,
            length=150,
            width=12,
            showvalue=0,
            resolution=1,
            bg=UI_BG,
            troughcolor=UI_SURFACE,
            highlightthickness=0,
            bd=0,
            activebackground=UI_ACCENT_DIM,
            fg=UI_ACCENT_DIM,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Label(speed_row, text="fast", style="Tag.TLabel").pack(side=tk.LEFT)

        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1, minsize=320)
        body.rowconfigure(1, weight=1)

        top_nav = ttk.Frame(body)
        top_nav.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._build_left_nav(top_nav)

        content_shell = ttk.Frame(body)
        content_shell.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        content_shell.rowconfigure(0, weight=1)
        content_shell.columnconfigure(0, weight=1)

        start_tab = ttk.Frame(content_shell)
        status_tab = ttk.Frame(content_shell)
        tools_tab = ttk.Frame(content_shell)
        logs_tab = ttk.Frame(content_shell)
        config_tab = ttk.Frame(content_shell)
        catalog_tab = ttk.Frame(content_shell)
        happ_ops_tab = ttk.Frame(content_shell)
        backup_tab = ttk.Frame(content_shell)
        guide_tab = ttk.Frame(content_shell)

        self.tab_frames = {
            "Start Here": start_tab,
            "Status & Stats": status_tab,
            "Tools": tools_tab,
            "Logs": logs_tab,
            "hApp Config": config_tab,
            "App Catalog": catalog_tab,
            "hApp Ops": happ_ops_tab,
            "Data Backup": backup_tab,
            "After Install": guide_tab,
        }

        self._build_start_tab(start_tab)
        self._build_status_tab(status_tab)
        self._build_tools_tab(tools_tab)
        self._build_logs_tab(logs_tab)
        self._build_config_tab(config_tab)
        self._build_catalog_tab(catalog_tab)
        self._build_happ_ops_tab(happ_ops_tab)
        self._build_backup_tab(backup_tab)
        self._build_after_install_tab(guide_tab)

        for name, frame in self.tab_frames.items():
            frame.grid(row=0, column=0, sticky="nsew")
            frame.grid_remove()
        self.show_tab("Start Here")

        self._build_right_hosting_panel(body)

    def _build_left_nav(self, parent):
        nav_items = [
            ("Start Here", "Home"),
            ("Status & Stats", "Status"),
            ("Tools", "Tools"),
            ("App Catalog", "Apps"),
            ("hApp Ops", "Install"),
            ("hApp Config", "Config"),
            ("Data Backup", "Backup"),
            ("Logs", "Logs"),
            ("After Install", "After"),
        ]
        strip = tk.Frame(parent, bg=UI_SURFACE, highlightthickness=1, highlightbackground=UI_BORDER_STRONG)
        strip.pack(fill=tk.X)
        for name, label in nav_items:
            btn = tk.Button(
                strip,
                text=label,
                relief=tk.FLAT,
                bd=0,
                bg=UI_SURFACE,
                fg=UI_TEXT,
                activebackground=UI_RISE,
                activeforeground=UI_ACCENT_DIM,
                font=("Segoe UI", 9),
                padx=10,
                pady=7,
                cursor="hand2",
                command=lambda n=name: self.show_tab(n),
            )
            btn.pack(side=tk.LEFT, padx=3, pady=4)
            self.nav_row_frames[name] = (btn, None, None)

    def show_tab(self, name):
        if name not in self.tab_frames:
            return
        self.current_tab_name = name
        for n, frame in self.tab_frames.items():
            if n == name:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_remove()
        for n, widgets in self.nav_row_frames.items():
            row, ic, lb = widgets
            active = n == name
            bg = UI_RISE if active else UI_SURFACE
            fg_txt = UI_ACCENT_DIM if active else UI_TEXT
            try:
                row.configure(bg=bg, fg=fg_txt)
            except tk.TclError:
                row.configure(bg=bg)
            if ic is not None:
                ic.configure(bg=bg, fg=(UI_ACCENT if active else UI_TEXT_MUTE))
            if lb is not None:
                lb.configure(bg=bg, fg=fg_txt)

    def _build_right_hosting_panel(self, parent):
        """Narrow right column: live status summary."""
        wrap = ttk.Frame(parent)
        wrap.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        host = tk.Frame(wrap, bg=UI_SURFACE, highlightthickness=1, highlightbackground=UI_BORDER_STRONG)
        host.grid(row=0, column=0, sticky="nsew")
        host.rowconfigure(1, weight=1)
        host.columnconfigure(0, weight=1)
        tk.Label(
            host,
            textvariable=self.hosting_title_var,
            bg=UI_SURFACE,
            fg=UI_ACCENT_DIM,
            font=("Segoe UI Semibold", 10),
            anchor="w",
            padx=12,
            pady=8,
        ).grid(row=0, column=0, sticky="ew")
        hosting_text = tk.Text(
            host,
            height=4,
            wrap="word",
            bg=UI_INPUT_BG,
            fg=UI_TEXT,
            relief=tk.FLAT,
            highlightthickness=0,
            padx=10,
            pady=8,
            font=("Segoe UI", 11),
            insertbackground=UI_ACCENT,
        )
        hosting_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        hosting_text.insert(
            tk.END,
            "Loading live status...",
        )
        hosting_text.configure(state=tk.DISABLED)
        self.hosting_text = hosting_text

    def _build_start_tab(self, parent):
        hero = tk.Frame(parent, bg=UI_BG)
        hero.pack(fill=tk.X, padx=14, pady=(14, 8))
        tk.Label(
            hero,
            text="You are one flow away from a running edge node.",
            bg=UI_BG,
            fg=UI_ACCENT_DIM,
            font=("Segoe UI Semibold", 13),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            hero,
            text=(
                "BroNode talks to Docker Desktop. Follow the steps below in order — after each major step "
                "you will be asked whether to continue to the next one."
            ),
            bg=UI_BG,
            fg=UI_TEXT_MUTE,
            font=("Segoe UI", 10),
            anchor="w",
            justify=tk.LEFT,
            wraplength=720,
        ).pack(anchor="w", pady=(6, 0))

        self.wizard_step1_status = tk.StringVar(value="Checking…")
        self.wizard_step2_status = tk.StringVar(value="…")
        self.wizard_step3_status = tk.StringVar(value="…")

        card = tk.Frame(parent, bg=UI_SURFACE, highlightthickness=1, highlightbackground=UI_BORDER_STRONG)
        card.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 10))
        tk.Label(
            card,
            text="Setup path",
            bg=UI_SURFACE,
            fg=UI_ACCENT_DIM,
            font=("Segoe UI Semibold", 12),
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 4))

        self._wizard_step_block(
            card,
            "1 · Pull the Edge Node image",
            "Downloads the container image from the registry (first time can take several minutes).",
            self.wizard_step1_status,
            "Pull image",
            self.wizard_pull_image,
            "wizard_btn_step1",
        )
        self._wizard_step_block(
            card,
            "2 · Run the container",
            "Creates the named container if needed, or starts it if it already exists.",
            self.wizard_step2_status,
            "Run / start container",
            self.wizard_run_container_step,
            "wizard_btn_step2",
        )
        self._wizard_step_block(
            card,
            "3 · Choose an app",
            "Pick a catalog preset and generate config when you are ready.",
            self.wizard_step3_status,
            "Open App Catalog",
            self.wizard_open_catalog,
            "wizard_btn_step3",
        )
        row4 = ttk.Frame(card)
        row4.pack(fill=tk.X, padx=12, pady=(4, 6))
        ttk.Label(row4, text="4 · Install & enable", style="Field.TLabel").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(row4, text="Open hApp Ops…", command=self.wizard_open_happ_ops).pack(side=tk.LEFT, padx=(0, 8))
        row5 = ttk.Frame(card)
        row5.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Label(row5, text="5 · Verify", style="Field.TLabel").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(row5, text="Open Status & Logs…", command=self.wizard_open_verify).pack(side=tk.LEFT)

        ttk.Label(
            parent,
            text=(
                "Advanced: change image or volume on the Tools tab. If something fails, check Logs and Status."
            ),
            style="Subtle.TLabel",
            justify=tk.LEFT,
            wraplength=720,
        ).pack(anchor="w", padx=14, pady=(0, 8))
        ttk.Frame(parent).pack(fill=tk.BOTH, expand=True)

    def _wizard_step_block(self, parent, title, subtitle, status_var, btn_label, command, btn_attr_name):
        row = tk.Frame(parent, bg=UI_SURFACE)
        row.pack(fill=tk.X, padx=12, pady=8)
        inner = tk.Frame(row, bg=UI_SURFACE)
        inner.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(
            inner,
            text=title,
            bg=UI_SURFACE,
            fg=UI_TEXT,
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            inner,
            text=subtitle,
            bg=UI_SURFACE,
            fg=UI_TEXT_MUTE,
            font=("Segoe UI", 9),
            anchor="w",
            wraplength=520,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(2, 0))
        tk.Label(
            inner,
            textvariable=status_var,
            bg=UI_SURFACE,
            fg=UI_ACCENT_DIM,
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))
        b = ttk.Button(row, text=btn_label, width=22, command=command)
        b.pack(side=tk.RIGHT, padx=(12, 0))
        setattr(self, btn_attr_name, b)

    def _query_wizard_state(self):
        image = self.image_var.get().strip() or DEFAULT_IMAGE
        img_code, _, _ = run_command(["docker", "image", "inspect", image], timeout=25)
        has_image = img_code == 0
        inspect_code, inspect_out, _ = run_command(
            ["docker", "inspect", CONTAINER_NAME, "--format", "{{.State.Running}}"],
            timeout=20,
        )
        exists = inspect_code == 0
        running = exists and (inspect_out or "").strip().lower() == "true"
        return {"has_image": has_image, "container_exists": exists, "running": running}

    def _refresh_start_wizard_ui(self):
        if getattr(self, "wizard_step1_status", None) is None:
            return
        st = self._query_wizard_state()
        if st["has_image"]:
            self.wizard_step1_status.set("Image present — you can pull again to refresh.")
        else:
            self.wizard_step1_status.set("Image not found locally yet — pull first.")
        if st["running"]:
            self.wizard_step2_status.set("Container is running.")
        elif st["container_exists"]:
            self.wizard_step2_status.set("Container exists but is stopped — start it to continue.")
        else:
            self.wizard_step2_status.set("Container not created yet — run after the image is present.")
        if st["running"]:
            self.wizard_step3_status.set("Node is up — choose a catalog preset next.")
        else:
            self.wizard_step3_status.set("Complete steps 1–2 first, then pick an app.")

        for btn, enabled in (
            (getattr(self, "wizard_btn_step1", None), True),
            (getattr(self, "wizard_btn_step2", None), st["has_image"]),
            (getattr(self, "wizard_btn_step3", None), st["running"]),
        ):
            if btn is not None:
                btn.state(["!disabled"] if enabled else ["disabled"])

    def wizard_pull_image(self):
        if not self.dependencies_ready:
            self.ui_warn("Docker", "Waiting for Docker Desktop — check the indicator top-right.")
            return
        image = self.image_var.get().strip() or DEFAULT_IMAGE
        self.pull_image_with_progress(image, on_complete=self._wizard_after_pull)

    def _wizard_after_pull(self, success, message):
        if not success:
            self.ui_error(
                "Image Pull Failed",
                (message or "Unable to pull image.")
                + "\n\nTip: verify internet access, Docker login, and image name.",
            )
            self.root.after(1500, self.ensure_dependencies_and_continue)
            return
        self.refresh_all()
        if self.ui_confirm(
            "Start container",
            "Create or start the Edge Node container now?\n\n"
            "This creates the container if it does not exist, or starts it if it stopped.",
        ):
            self.run_container(on_success=self._wizard_prompt_app_catalog, quiet=True)

    def _wizard_prompt_app_catalog(self):
        self.refresh_all()
        if self.ui_confirm(
            "Choose an app",
            "Open the App Catalog to pick a preset?\n\n"
            "You can skip for now and use the navigation bar anytime.",
        ):
            self.show_tab("App Catalog")

    def wizard_run_container_step(self):
        if not self.dependencies_ready:
            self.ui_warn("Docker", "Waiting for Docker Desktop — check the indicator top-right.")
            return
        st = self._query_wizard_state()
        if not st["has_image"]:
            self.ui_warn("Image required", "Pull the Edge Node image in step 1 first (Tools tab if you prefer).")
            return
        self.run_container(on_success=self._wizard_prompt_app_catalog, quiet=False)

    def wizard_open_catalog(self):
        if not self.ui_confirm(
            "App Catalog",
            "Open the App Catalog to pick a preset?",
        ):
            return
        self.show_tab("App Catalog")

    def wizard_open_happ_ops(self):
        if not self.ui_confirm(
            "hApp Ops",
            "Open hApp Ops to install and enable your app?",
        ):
            return
        self.show_tab("hApp Ops")

    def wizard_open_verify(self):
        if not self.ui_confirm(
            "Verify",
            "Open Status & Stats to check the node, and use Logs for output?",
        ):
            return
        self.show_tab("Status & Stats")

    def _on_tab_changed(self, _event=None):
        pass

    def goto_tab(self, tab_name):
        self.show_tab(tab_name)

    def _build_dependency_widget(self, parent):
        wrap = ttk.Frame(parent)
        wrap.pack(side=tk.RIGHT, padx=(8, 14))
        ttk.Label(wrap, textvariable=self.dep_status_var, style="Subtle.TLabel").pack(anchor="e")
        self.dep_canvas = tk.Canvas(
            wrap, width=240, height=34, bg=UI_DEEP, highlightthickness=1, highlightbackground=UI_BORDER_STRONG, bd=0, relief=tk.FLAT
        )
        self.dep_canvas.pack(anchor="e")
        self.dep_action_button = ttk.Button(
            wrap, textvariable=self.dep_action_var, command=self.handle_dependency_action
        )
        self.dep_action_button.pack(anchor="e", pady=(4, 0))
        self._draw_dependency_status({"python": True, "docker": False, "cairosvg": False})

    def _build_status_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        row = 0
        for key, var in self.status_vars.items():
            ttk.Label(parent, text=f"{key}:", width=14, style="Subtle.TLabel").grid(
                row=row, column=0, sticky="w", padx=10, pady=4
            )
            ttk.Label(parent, textvariable=var).grid(
                row=row, column=1, sticky="w", padx=10, pady=4
            )
            row += 1

        net_row = ttk.Frame(parent)
        net_row.grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 6))
        ttk.Button(net_row, text="Copy Local IP", command=self.copy_local_ip_to_clipboard).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        ttk.Label(
            net_row,
            text="Copies the Local IP value to the system clipboard.",
            style="Subtle.TLabel",
        ).pack(side=tk.LEFT)
        row += 1

        ttk.Separator(parent, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=10
        )
        row += 1

        for key, var in self.stats_vars.items():
            ttk.Label(parent, text=f"{key}:", width=14).grid(
                row=row, column=0, sticky="w", padx=10, pady=4
            )
            ttk.Label(parent, textvariable=var).grid(
                row=row, column=1, sticky="w", padx=10, pady=4
            )
            row += 1

        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=16)

        ttk.Button(button_frame, text="Refresh Now", command=self.refresh_all).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(
            button_frame, text="Auto Refresh (5s)", command=self.start_auto_refresh
        ).pack(side=tk.LEFT)

        ttk.Label(parent, text="CPU / Mem history (last 60 samples):").grid(
            row=row + 1, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 4)
        )
        self.chart_canvas = tk.Canvas(
            parent,
            height=220,
            bg=UI_DEEP,
            highlightthickness=1,
            highlightbackground=UI_BORDER_STRONG,
        )
        self.chart_canvas.grid(row=row + 2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
        parent.rowconfigure(row + 2, weight=1)
        self.chart_canvas.bind("<Configure>", lambda _e: self._draw_history_chart())

    def _build_tools_tab(self, parent):
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="Image:", width=10, style="Field.TLabel").grid(
            row=0, column=0, sticky="nw", padx=10, pady=10
        )
        ttk.Entry(parent, textvariable=self.image_var).grid(
            row=0, column=1, sticky="ew", padx=10, pady=10
        )
        ttk.Label(parent, text="Volume:", width=10, style="Field.TLabel").grid(
            row=1, column=0, sticky="nw", padx=10, pady=10
        )
        ttk.Entry(parent, textvariable=self.volume_var).grid(
            row=1, column=1, sticky="ew", padx=10, pady=10
        )

        actions = [
            ("Pull Image", self.pull_image),
            ("Run Container", self.run_container),
            ("Start", self.start_container),
            ("Stop", self.stop_container),
            ("Restart", self.restart_container),
            ("Uninstall Node Setup", self.uninstall_node_setup),
            ("Open Shell", self.open_shell),
            ("Follow Logs", self.follow_logs_external),
        ]

        row = 2
        col = 0
        for label, handler in actions:
            style_name = "Secondary.TButton" if label in ("Open Shell", "Follow Logs", "Uninstall Node Setup") else "TButton"
            ttk.Button(parent, text=label, command=handler, width=22, style=style_name).grid(
                row=row, column=col, padx=10, pady=8, sticky="w"
            )
            col += 1
            if col > 1:
                col = 0
                row += 1

    def _build_logs_tab(self, parent):
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.logs_text = tk.Text(
            parent,
            wrap="word",
            bg=UI_INPUT_BG,
            fg=UI_TEXT,
            insertbackground=UI_ACCENT,
            highlightthickness=1,
            highlightbackground=UI_BORDER_STRONG,
            relief=tk.FLAT,
            font=FONT_MONO_SM,
        )
        self.logs_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        button_frame = ttk.Frame(parent)
        button_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        ttk.Button(button_frame, text="Refresh Logs", command=self.refresh_logs).pack(
            side=tk.LEFT
        )
        ttk.Button(button_frame, text="Clear", command=self.clear_logs).pack(
            side=tk.LEFT, padx=(8, 0)
        )

    def _build_config_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        ttk.Label(
            parent,
            text=(
                "Create and validate Edge Node install configs.\n"
                "Use this when preparing a .happ/.webhapp deployment for always-on nodes.\n"
                "Tip: use iroh for newer Holochain networking defaults."
            ),
            style="Subtle.TLabel",
            justify=tk.LEFT,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 12))

        ttk.Entry(parent, textvariable=self.config_tool_path_var, width=70).grid(
            row=1, column=1, sticky="ew", padx=10, pady=8
        )
        ttk.Button(parent, text="Browse", command=self.pick_config_tool).grid(
            row=1, column=2, sticky="w", padx=10, pady=8
        )

        ttk.Label(parent, text="CLI path:", width=12).grid(row=1, column=0, sticky="w", padx=10, pady=8)
        ttk.Label(parent, text="Config name:", width=12).grid(row=2, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(parent, textvariable=self.config_name_var, width=24).grid(
            row=2, column=1, sticky="w", padx=10, pady=8
        )

        flags_frame = ttk.Frame(parent)
        flags_frame.grid(row=3, column=1, sticky="w", padx=10, pady=8)
        ttk.Checkbutton(flags_frame, text="iroh", variable=self.config_iroh_var).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(flags_frame, text="gateway", variable=self.config_gateway_var).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(flags_frame, text="economics", variable=self.config_economics_var).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(flags_frame, text="init-zome-calls", variable=self.config_init_zome_var).pack(side=tk.LEFT)

        ttk.Button(parent, text="Create Config", command=self.create_happ_config).grid(
            row=4, column=1, sticky="w", padx=10, pady=8
        )

        ttk.Separator(parent, orient="horizontal").grid(row=5, column=0, columnspan=3, sticky="ew", padx=10, pady=12)

        ttk.Label(parent, text="Input config:", width=12).grid(row=6, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(parent, textvariable=self.config_input_var, width=70).grid(
            row=6, column=1, sticky="ew", padx=10, pady=8
        )
        ttk.Button(parent, text="Browse", command=self.pick_input_config).grid(
            row=6, column=2, sticky="w", padx=10, pady=8
        )

        ttk.Button(parent, text="Validate Config", command=self.validate_happ_config).grid(
            row=7, column=1, sticky="w", padx=10, pady=8
        )

        ttk.Label(
            parent,
            text=(
                "Fields map to Edge Node config sections:\n"
                "- app: name/version/happ URL/modifiers\n"
                "- env.holochain: bootstrap + networking\n"
                "- optional gw/economics/init_zome_calls"
            ),
            style="Subtle.TLabel",
            justify=tk.LEFT,
        ).grid(row=8, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 0))

    def _build_happ_ops_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(4, weight=1)

        ttk.Label(
            parent,
            text=(
                "Operate hApps inside the Edge Node container.\n"
                "Commands: install_happ, list_happs, enable_happ, disable_happ, uninstall_happ."
            ),
            style="Subtle.TLabel",
            justify=tk.LEFT,
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 10))

        install_fr = ttk.LabelFrame(parent, text="  Install & list  ", style="Card.TLabelframe")
        install_fr.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        install_fr.columnconfigure(1, weight=1)

        ttk.Label(install_fr, text="Config file:", width=12, style="Field.TLabel").grid(
            row=0, column=0, sticky="nw", padx=10, pady=8
        )
        ttk.Entry(install_fr, textvariable=self.install_config_var).grid(
            row=0, column=1, sticky="ew", padx=10, pady=8
        )
        ttk.Button(install_fr, text="Browse", command=self.pick_install_config).grid(
            row=0, column=2, sticky="w", padx=10, pady=8
        )

        ttk.Label(install_fr, text="Node name:", width=12, style="Field.TLabel").grid(
            row=1, column=0, sticky="w", padx=10, pady=8
        )
        ttk.Entry(install_fr, textvariable=self.node_name_var, width=28).grid(
            row=1, column=1, sticky="w", padx=10, pady=8
        )
        ttk.Label(install_fr, text="Admin port:", width=12, style="Field.TLabel").grid(
            row=1, column=2, sticky="e", padx=10, pady=8
        )
        ttk.Entry(install_fr, textvariable=self.admin_port_var, width=12).grid(
            row=1, column=3, sticky="w", padx=10, pady=8
        )

        ttk.Button(install_fr, text="Install hApp", command=self.install_happ).grid(
            row=2, column=0, sticky="w", padx=10, pady=10
        )
        ttk.Button(install_fr, text="List hApps", command=self.list_happs).grid(
            row=2, column=1, sticky="w", padx=10, pady=10
        )
        ttk.Checkbutton(install_fr, text="Show raw command output", variable=self.show_raw_output_var).grid(
            row=2, column=2, columnspan=2, sticky="w", padx=10, pady=10
        )

        life_fr = ttk.LabelFrame(parent, text="  Enable / disable / uninstall  ", style="Card.TLabelframe")
        life_fr.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))
        life_fr.columnconfigure(1, weight=1)

        ttk.Label(life_fr, text="App ID:", width=12, style="Field.TLabel").grid(
            row=0, column=0, sticky="nw", padx=10, pady=8
        )
        ttk.Entry(life_fr, textvariable=self.app_id_var).grid(
            row=0, column=1, columnspan=3, sticky="ew", padx=10, pady=8
        )
        ttk.Button(life_fr, text="Enable", command=self.enable_happ).grid(
            row=1, column=0, sticky="w", padx=10, pady=10
        )
        ttk.Button(life_fr, text="Disable", command=self.disable_happ).grid(
            row=1, column=1, sticky="w", padx=10, pady=10
        )
        ttk.Button(life_fr, text="Uninstall", command=self.uninstall_happ).grid(
            row=1, column=2, sticky="w", padx=10, pady=10
        )

        apps_fr = ttk.LabelFrame(parent, text="  Installed apps  ", style="Card.TLabelframe")
        apps_fr.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 8))
        apps_fr.columnconfigure(0, weight=1)
        apps_fr.rowconfigure(1, weight=1)

        summary = ttk.Frame(apps_fr)
        summary.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 6))
        ttk.Label(summary, textvariable=self.apps_count_var, style="Subtle.TLabel").pack(side=tk.LEFT, padx=(0, 16))
        ttk.Label(summary, textvariable=self.apps_enabled_var, style="Subtle.TLabel").pack(side=tk.LEFT, padx=(0, 16))
        ttk.Label(summary, textvariable=self.apps_last_var, style="Subtle.TLabel").pack(side=tk.LEFT)

        tree_wrap = ttk.Frame(apps_fr)
        tree_wrap.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)

        columns = ("app", "status", "version", "installed_at")
        self.apps_tree = ttk.Treeview(tree_wrap, columns=columns, show="headings", height=7)
        self.apps_tree.heading("app", text="App ID")
        self.apps_tree.heading("status", text="Status")
        self.apps_tree.heading("version", text="Version")
        self.apps_tree.heading("installed_at", text="Installed At")
        self.apps_tree.column("app", width=420, anchor="w")
        self.apps_tree.column("status", width=90, anchor="center")
        self.apps_tree.column("version", width=90, anchor="center")
        self.apps_tree.column("installed_at", width=180, anchor="center")
        self.apps_tree.grid(row=0, column=0, sticky="nsew")
        for col in columns:
            self.apps_tree.column(col, stretch=True, minwidth=48)
        self.apps_tree.bind("<<TreeviewSelect>>", self.on_happ_selected)
        yscroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.apps_tree.yview)
        self.apps_tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns")

        out_fr = ttk.LabelFrame(parent, text="  Command output  ", style="Card.TLabelframe")
        out_fr.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0, 8))
        out_fr.columnconfigure(0, weight=1)
        out_fr.rowconfigure(0, weight=1)

        ops_wrap = tk.Text(
            out_fr,
            height=12,
            wrap="word",
            bg=UI_INPUT_BG,
            fg=UI_TEXT,
            insertbackground=UI_ACCENT,
            highlightthickness=1,
            highlightbackground=UI_BORDER_STRONG,
            relief=tk.FLAT,
            font=FONT_MONO_SM,
        )
        ops_wrap.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.ops_output_text = ops_wrap

    def _build_catalog_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)
        parent.rowconfigure(2, weight=1)
        ttk.Label(
            parent,
            text=(
                "Quick-start catalog for hApps you can run on this node.\n"
                "Choose a preset, generate config, then install from hApp Ops."
            ),
            style="Subtle.TLabel",
            justify=tk.LEFT,
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(8, 12))

        ttk.Label(parent, text="Preset:", width=12).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 6))
        preset_box = ttk.Combobox(
            parent,
            textvariable=self.catalog_choice_var,
            values=[item["label"] for item in APP_CATALOG],
            state="readonly",
            width=36,
        )
        preset_box.grid(row=1, column=1, sticky="w", padx=10, pady=(0, 6))
        preset_box.bind("<<ComboboxSelected>>", self.on_catalog_selected)
        ttk.Button(parent, text="Use selected preset", command=self.on_catalog_selected, style="Secondary.TButton").grid(
            row=1, column=2, sticky="w", padx=10, pady=(0, 6)
        )

        list_fr = ttk.LabelFrame(parent, text="  Available catalog apps  ", style="Card.TLabelframe")
        list_fr.grid(row=2, column=0, columnspan=4, sticky="nsew", padx=10, pady=(0, 8))
        list_fr.columnconfigure(0, weight=1)
        list_fr.rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            list_fr,
            columns=("preset", "hostable", "url"),
            show="headings",
            height=4,
        )
        tree.heading("preset", text="Preset")
        tree.heading("hostable", text="Hostable now")
        tree.heading("url", text="hApp URL")
        tree.column("preset", width=220, anchor="w")
        tree.column("hostable", width=110, anchor="center")
        tree.column("url", width=520, anchor="w")
        tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        ysb = ttk.Scrollbar(list_fr, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=ysb.set)
        ysb.grid(row=0, column=1, sticky="ns", pady=8)
        tree.bind("<<TreeviewSelect>>", self._on_catalog_tree_selected)
        self.catalog_tree = tree
        self._populate_catalog_tree()

        ttk.Label(parent, text="App name:", width=12).grid(row=3, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(parent, textvariable=self.catalog_name_var, width=28).grid(row=3, column=1, sticky="w", padx=10, pady=6)
        ttk.Label(parent, text="Version:", width=12).grid(row=3, column=2, sticky="e", padx=10, pady=6)
        ttk.Entry(parent, textvariable=self.catalog_version_var, width=18).grid(row=3, column=3, sticky="w", padx=10, pady=6)

        ttk.Label(parent, text="hApp URL:", width=12).grid(row=4, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(parent, textvariable=self.catalog_url_var, width=74).grid(row=4, column=1, columnspan=3, sticky="ew", padx=10, pady=6)

        ttk.Label(parent, text="Network seed:", width=12).grid(row=5, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(parent, textvariable=self.catalog_seed_var, width=36).grid(row=5, column=1, sticky="w", padx=10, pady=6)
        ttk.Checkbutton(parent, text="Use iroh networking", variable=self.config_iroh_var).grid(
            row=5, column=2, columnspan=2, sticky="w", padx=10, pady=6
        )

        ttk.Button(parent, text="Generate Config JSON", command=self.generate_catalog_config).grid(
            row=6, column=1, sticky="w", padx=10, pady=8
        )
        ttk.Button(parent, text="Use In hApp Ops", style="Secondary.TButton", command=self.use_catalog_in_ops).grid(
            row=6, column=2, sticky="w", padx=10, pady=8
        )
        ttk.Button(parent, text="Host Selected App", command=self.host_selected_catalog_app).grid(
            row=6, column=3, sticky="w", padx=10, pady=8
        )

        ttk.Separator(parent, orient="horizontal").grid(row=7, column=0, columnspan=4, sticky="ew", padx=10, pady=10)
        ttk.Label(parent, text="Preset notes:", width=12).grid(row=8, column=0, sticky="nw", padx=10, pady=6)
        ttk.Label(parent, textvariable=self.catalog_info_var, style="Subtle.TLabel", justify=tk.LEFT).grid(
            row=8, column=1, columnspan=3, sticky="ew", padx=10, pady=6
        )

    def _build_after_install_tab(self, parent):
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        ttk.Label(
            parent,
            text=(
                "What to do after your hApp is installed on BroNode.\n"
                "These steps are based on Edge Node operator guidance."
            ),
            style="Subtle.TLabel",
            justify=tk.LEFT,
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 10))

        guide = tk.Text(
            parent,
            wrap="word",
            bg=UI_INPUT_BG,
            fg=UI_TEXT,
            insertbackground=UI_ACCENT,
            highlightthickness=1,
            highlightbackground=UI_BORDER_STRONG,
            relief=tk.FLAT,
            font=FONT_MONO_SM,
        )
        guide.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        guide.insert(
            tk.END,
            (
                "POST-INSTALL CHECKLIST\n"
                "======================\n\n"
                "1) VERIFY INSTALLATION\n"
                "   - Open hApp Ops tab\n"
                "   - Click 'List hApps'\n"
                "   - Confirm your app appears in the list\n\n"
                "2) CONFIRM APP STATE\n"
                "   - If needed, use 'Enable' with app ID\n"
                "   - If troubleshooting, use 'Disable' then 'Enable' again\n\n"
                "3) MONITOR NODE HEALTH\n"
                "   - Status & Stats tab should show container running\n"
                "   - Watch CPU/MEM trends and logs for startup errors\n"
                "   - Logs tab should show conductor activity after install\n\n"
                "4) VERIFY NETWORK SETTINGS\n"
                "   - Ensure config network seed matches your target network\n"
                "   - For newer setups, prefer iroh relay configuration\n"
                "   - Wrong seed = node joins a different network and appears 'empty'\n\n"
                "5) OPERATIONAL HARDENING\n"
                "   - Keep Docker Desktop auto-start enabled\n"
                "   - Keep backup snapshots of volume (Data Backup tab)\n"
                "   - Record app IDs for enable/disable/uninstall actions\n\n"
                "6) LOGS & TROUBLESHOOTING\n"
                "   - Use Follow Logs for real-time view\n"
                "   - Common issue: container not running -> Start container first\n"
                "   - If install fails, validate config again and verify happ URL\n\n"
                "7) UPDATES / CHANGES\n"
                "   - Pull latest image before major updates\n"
                "   - Reinstall/upgrade apps with updated config versions\n"
                "   - Re-check list_happs and status after update\n\n"
                "8) UNINSTALL SAFETY\n"
                "   - In Tools: 'Uninstall Node Setup' removes container/image/volume data\n"
                "   - Take a backup first if you may need to restore state\n\n"
                "QUICK SUCCESS PATH\n"
                "------------------\n"
                "Pull Image -> Run Container -> Generate/Validate Config -> Install hApp -> List hApps -> Monitor Logs\n"
            ),
        )
        guide.configure(state=tk.DISABLED)

    def _build_backup_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text="Volume:", width=12).grid(row=0, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(parent, textvariable=self.volume_var, width=30).grid(
            row=0, column=1, sticky="ew", padx=10, pady=8
        )

        ttk.Label(parent, text="Backup dir:", width=12).grid(row=1, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(parent, textvariable=self.backup_dir_var, width=70).grid(
            row=1, column=1, sticky="ew", padx=10, pady=8
        )
        ttk.Button(parent, text="Browse", command=self.pick_backup_dir).grid(
            row=1, column=2, sticky="w", padx=10, pady=8
        )
        ttk.Button(parent, text="Create Backup", command=self.backup_volume).grid(
            row=2, column=1, sticky="w", padx=10, pady=8
        )

        ttk.Separator(parent, orient="horizontal").grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=12)

        ttk.Label(parent, text="Restore file:", width=12).grid(row=4, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(parent, textvariable=self.restore_file_var, width=70).grid(
            row=4, column=1, sticky="ew", padx=10, pady=8
        )
        ttk.Button(parent, text="Browse", command=self.pick_restore_file).grid(
            row=4, column=2, sticky="w", padx=10, pady=8
        )
        ttk.Button(parent, text="Restore Backup", command=self.restore_volume).grid(
            row=5, column=1, sticky="w", padx=10, pady=8
        )

    def set_log(self, text):
        self.logs_text.delete("1.0", tk.END)
        self.logs_text.insert(tk.END, text)

    def _center_toplevel(self, win, min_w=520, min_h=220, max_h_ratio=0.85):
        """Place window centered over the main BroNode window (not screen origin / top-left)."""
        parent = self.root
        parent.update_idletasks()
        win.update_idletasks()
        w = max(min_w, win.winfo_reqwidth() + 24)
        h = max(min_h, win.winfo_reqheight() + 16)
        sh_screen = win.winfo_screenheight()
        h = min(h, int(sh_screen * max_h_ratio))

        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = max(parent.winfo_width(), min_w)
        ph = max(parent.winfo_height(), min_h)

        x = px + (pw - w) // 2
        y = py + (ph - h) // 2

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max(0, min(x, max(0, sw - w)))
        y = max(0, min(y, max(0, sh - h)))

        win.geometry(f"{w}x{h}+{x}+{y}")

    def _on_app_close(self):
        """Always allow quitting: release grabs and tear down dialogs (Windows can hang otherwise)."""
        if self.auto_refresh_job is not None:
            try:
                self.root.after_cancel(self.auto_refresh_job)
            except tk.TclError:
                pass
            self.auto_refresh_job = None
        for child in list(self.root.winfo_children()):
            if isinstance(child, tk.Toplevel):
                try:
                    child.grab_release()
                except tk.TclError:
                    pass
                try:
                    child.destroy()
                except tk.TclError:
                    pass
        try:
            self.root.grab_release()
        except tk.TclError:
            pass
        self.root.destroy()

    def _show_dialog(self, kind, title, text, buttons=("OK",)):
        dlg = tk.Toplevel(self.root)
        dlg.withdraw()
        dlg.title(title)
        dlg.transient(self.root)
        dlg.configure(bg=UI_BG)
        dlg.resizable(True, True)
        dlg.minsize(480, 200)

        intros = {
            "info": "Notice — read the summary below. Nothing else is required unless you want to take action.",
            "warn": "Heads-up — please read carefully. Your choice may change how BroNode behaves.",
            "error": "This action did not finish. Below is what went wrong and what you can try next.",
        }
        color = {"info": UI_ACCENT_DIM, "warn": UI_WARN, "error": UI_ERR}.get(kind, UI_ACCENT_DIM)

        header = tk.Frame(dlg, bg=UI_BG)
        header.pack(fill=tk.X, padx=16, pady=(14, 6))
        tk.Label(
            header,
            text=title,
            bg=UI_BG,
            fg=color,
            font=("Segoe UI Semibold", 13),
            anchor="w",
            justify=tk.LEFT,
            wraplength=520,
        ).pack(fill=tk.X)

        tk.Label(
            dlg,
            text=intros.get(kind, intros["info"]),
            bg=UI_BG,
            fg=UI_TEXT_MUTE,
            font=("Segoe UI", 9),
            justify=tk.LEFT,
            anchor="w",
            wraplength=520,
            padx=16,
            pady=0,
        ).pack(fill=tk.X)

        sep = tk.Frame(dlg, bg=UI_BORDER, height=1)
        sep.pack(fill=tk.X, padx=16, pady=(4, 8))

        body = tk.Frame(dlg, bg=UI_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        text_widget = tk.Text(
            body,
            wrap="word",
            height=12,
            width=64,
            bg=UI_INPUT_BG,
            fg=UI_TEXT,
            insertbackground=UI_ACCENT,
            highlightthickness=1,
            highlightbackground=UI_BORDER_STRONG,
            relief=tk.FLAT,
            font=("Segoe UI", 10),
            padx=12,
            pady=10,
        )
        scroll = tk.Scrollbar(body, orient=tk.VERTICAL, command=text_widget.yview, bg=UI_INPUT_BG)
        text_widget.configure(yscrollcommand=scroll.set)
        text_widget.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        text_widget.insert(tk.END, text or "")
        text_widget.configure(state=tk.DISABLED)

        foot_text = (
            "Cancel keeps your current setup unchanged. Continue proceeds with the action described above."
            if len(buttons) > 1
            else "Tip: after closing, check Status & Stats and Logs if something still looks wrong."
        )
        foot = tk.Label(
            dlg,
            text=foot_text,
            bg=UI_BG,
            fg=UI_TEXT_MUTE,
            font=("Segoe UI", 8),
            justify=tk.LEFT,
            wraplength=520,
            padx=16,
            pady=0,
        )
        foot.pack(fill=tk.X)

        result = {"value": buttons[0]}
        row = tk.Frame(dlg, bg=UI_BG)
        row.pack(fill=tk.X, padx=16, pady=(4, 14))
        for b in buttons:
            tk.Button(
                row,
                text=b,
                command=lambda v=b: (result.update({"value": v}), dlg.destroy()),
                bg=UI_RISE if b.lower() in ("ok", "yes", "continue") else UI_DEEP,
                fg=UI_ACCENT_DIM if b.lower() in ("ok", "yes", "continue") else UI_TEXT_MUTE,
                activebackground=UI_SURFACE,
                activeforeground=UI_TEXT,
                highlightthickness=1,
                highlightbackground=UI_BORDER_STRONG,
                relief=tk.FLAT,
                padx=16,
                pady=8,
            ).pack(side=tk.RIGHT, padx=(8, 0))

        self._center_toplevel(dlg, min_w=560, min_h=320)
        dlg.deiconify()
        dlg.lift(self.root)
        dlg.update_idletasks()
        dlg.focus_set()
        dlg.wait_window()
        try:
            self.root.focus_set()
        except tk.TclError:
            pass
        return result["value"]

    def ui_info(self, title, text):
        self._show_dialog("info", title, text, ("OK",))

    def ui_warn(self, title, text):
        self._show_dialog("warn", title, text, ("OK",))

    def ui_error(self, title, text):
        self._show_dialog("error", title, text, ("OK",))

    def ui_confirm(self, title, text):
        return self._show_dialog("warn", title, text, ("Cancel", "Continue")) == "Continue"

    def refresh_all(self):
        if not self.dependencies_ready:
            return
        self.refresh_network()
        self.refresh_status()
        self.refresh_stats()
        self.refresh_logs()
        self.refresh_banner_text()
        self.refresh_hosted_apps_if_due()
        self._update_hosting_panel(self.hosted_apps_cache)
        if getattr(self, "wizard_step1_status", None) is not None:
            self._refresh_start_wizard_ui()

    def start_auto_refresh(self):
        self.refresh_all()
        if self.auto_refresh_job is not None:
            self.root.after_cancel(self.auto_refresh_job)
        self.auto_refresh_job = self.root.after(5000, self.start_auto_refresh)

    def refresh_network(self):
        self.status_vars["Local IP"].set(get_local_ipv4())

    def copy_local_ip_to_clipboard(self):
        ip = (self.status_vars["Local IP"].get() or "").strip()
        if not ip or ip == "-":
            ip = get_local_ipv4()
            self.status_vars["Local IP"].set(ip)
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(ip)
            self.root.update_idletasks()
        except tk.TclError:
            self.ui_warn("Clipboard", "Could not copy to clipboard.")
            return
        self.action_status_var.set(f"Copied IP: {ip}")
        self.root.after(2800, lambda: self.action_status_var.set("Idle"))

    def refresh_status(self):
        # `docker version` alone can succeed for the CLI while the engine is down; `docker ps` needs a live daemon.
        code, _, err = run_command(["docker", "ps"], timeout=15)
        if code != 0:
            hint = "engine offline — start Docker Desktop" if is_docker_daemon_error(err or "") else (err or "daemon unreachable")
            self.status_vars["Docker"].set(f"Unavailable ({hint})")
            for key in ("Container", "Running", "Status", "Image", "StartedAt"):
                self.status_vars[key].set("-")
            return
        ver_code, ver_out, _ = run_command(["docker", "version", "--format", "{{.Server.Version}}"], timeout=10)
        self.status_vars["Docker"].set(ver_out or "OK" if ver_code == 0 else "OK")

        inspect_cmd = [
            "docker",
            "inspect",
            CONTAINER_NAME,
            "--format",
            "{{json .State}}|{{.Config.Image}}|{{.Name}}",
        ]
        code, out, err = run_command(inspect_cmd)
        if code != 0 or "|" not in out:
            self.status_vars["Container"].set(CONTAINER_NAME)
            self.status_vars["Running"].set("No")
            self.status_vars["Status"].set("Not found")
            self.status_vars["Image"].set("-")
            self.status_vars["StartedAt"].set("-")
            return

        state_json, image, name = out.split("|", 2)
        try:
            state = json.loads(state_json)
        except json.JSONDecodeError:
            state = {}
        self.status_vars["Container"].set(name.lstrip("/") or CONTAINER_NAME)
        self.status_vars["Running"].set("Yes" if state.get("Running") else "No")
        self.status_vars["Status"].set(state.get("Status", "-"))
        self.status_vars["Image"].set(image or "-")
        self.status_vars["StartedAt"].set(state.get("StartedAt", "-"))

    def refresh_stats(self):
        cmd = [
            "docker",
            "stats",
            CONTAINER_NAME,
            "--no-stream",
            "--format",
            "{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}|{{.BlockIO}}|{{.PIDs}}",
        ]
        code, out, _ = run_command(cmd)
        if code != 0 or "|" not in out:
            for key in self.stats_vars:
                self.stats_vars[key].set("-")
            self._draw_history_chart()
            return
        cpu, mem, net, block, pids = out.split("|", 4)
        self.stats_vars["CPU"].set(cpu)
        self.stats_vars["Memory"].set(mem)
        self.stats_vars["NetIO"].set(net)
        self.stats_vars["BlockIO"].set(block)
        self.stats_vars["PIDs"].set(pids)
        self._append_history(cpu, mem)
        self._draw_history_chart()

    def refresh_logs(self):
        cmd = ["docker", "logs", "--tail", "200", CONTAINER_NAME]
        code, out, err = run_command(cmd)
        if code != 0:
            if is_docker_daemon_error(err or out):
                self.set_log(format_docker_user_message(err or out))
                return
            if is_missing_container_error(err or out):
                self.set_log(
                    f"No container named '{CONTAINER_NAME}' exists yet.\n\n"
                    "Next step:\n"
                    "1) Start Here → Pull image, then Run / start container\n"
                    "2) Or use the Tools tab for the same actions\n\n"
                    "After that, logs will appear here."
                )
            else:
                self.set_log(f"Unable to read logs for '{CONTAINER_NAME}'.\n\n{err or out}")
            return
        self.set_log(out or "(No logs yet)")

    def clear_logs(self):
        self.logs_text.delete("1.0", tk.END)

    def notify(self, title, text):
        self.ui_info(title, text)
        self.refresh_all()

    def run_action(self, cmd, title):
        self._run_in_background(cmd, title, refresh_after=True, timeout=None)

    def _run_in_background(
        self,
        cmd,
        title,
        refresh_after=False,
        timeout=None,
        on_success=None,
        quiet=False,
    ):
        self.action_status_var.set(f"{title} running...")

        def worker():
            code, out, err = run_command(cmd, timeout=timeout)

            def done():
                if code == 0:
                    self.action_status_var.set("Idle")
                    if not quiet:
                        self.ui_info(title, out or "Done.")
                    if refresh_after:
                        self.refresh_all()
                    if on_success:
                        on_success()
                else:
                    raw = err or out or "Command failed."
                    msg = format_docker_user_message(raw)
                    if raw == msg:
                        msg = raw + "\n\nTip: check Docker status, container state, and Logs tab for details."
                    self.ui_error(title, msg)
                    if refresh_after:
                        self.refresh_all()
                    self.action_status_var.set("Idle")

            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _append_history(self, cpu_text, mem_text):
        cpu_val = self._parse_percent(cpu_text)
        mem_val = self._parse_memory_percent(mem_text)
        self.cpu_history.append(cpu_val)
        self.mem_history.append(mem_val)
        if len(self.cpu_history) > self.history_max_points:
            self.cpu_history = self.cpu_history[-self.history_max_points :]
        if len(self.mem_history) > self.history_max_points:
            self.mem_history = self.mem_history[-self.history_max_points :]

    def _draw_history_chart(self):
        if not self.chart_canvas:
            return
        c = self.chart_canvas
        c.delete("all")
        width = max(120, int(c.winfo_width() or 400))
        height = max(80, int(c.winfo_height() or 220))
        margin = 24
        c.create_rectangle(margin, margin, width - margin, height - margin, outline=UI_BORDER)
        c.create_text(margin, margin - 10, text="100%", fill=UI_TEXT_MUTE, anchor="w", font=FONT_MONO_SM)
        c.create_text(margin, height - margin + 10, text="0%", fill=UI_TEXT_MUTE, anchor="w", font=FONT_MONO_SM)

        if len(self.cpu_history) < 2:
            c.create_text(width // 2, height // 2, text="awaiting telemetry...", fill=UI_TEXT_MUTE, font=FONT_MONO_SM)
            return

        self._draw_series(c, self.cpu_history, UI_ACCENT, width, height, margin)
        self._draw_series(c, self.mem_history, UI_ACCENT_DIM, width, height, margin)
        c.create_text(width - margin - 140, margin - 10, text="CPU", fill=UI_ACCENT, anchor="w", font=FONT_MONO_SM)
        c.create_text(width - margin - 80, margin - 10, text="MEM", fill=UI_ACCENT_DIM, anchor="w", font=FONT_MONO_SM)

    def _draw_series(self, canvas, data, color, width, height, margin):
        plot_w = width - 2 * margin
        plot_h = height - 2 * margin
        steps = max(1, len(data) - 1)
        points = []
        for i, value in enumerate(data):
            x = margin + (plot_w * i / steps)
            y = margin + (plot_h * (1 - max(0.0, min(100.0, value)) / 100.0))
            points.extend([x, y])
        canvas.create_line(*points, fill=color, width=2, smooth=True)

    def _parse_percent(self, text):
        try:
            return float(text.replace("%", "").strip())
        except Exception:
            return 0.0

    def _parse_memory_percent(self, mem_text):
        # Docker format is usually "used / total". Convert to percent if possible.
        if "/" not in mem_text:
            return 0.0
        used, total = mem_text.split("/", 1)
        used_bytes = self._parse_size_to_bytes(used.strip())
        total_bytes = self._parse_size_to_bytes(total.strip())
        if total_bytes <= 0:
            return 0.0
        return (used_bytes / total_bytes) * 100.0

    def _parse_size_to_bytes(self, size_text):
        text = size_text.lower().replace("ib", "b").strip()
        units = {
            "kb": 1024,
            "mb": 1024**2,
            "gb": 1024**3,
            "tb": 1024**4,
            "b": 1,
        }
        for unit, factor in units.items():
            if text.endswith(unit):
                number = text[: -len(unit)].strip()
                try:
                    return float(number) * factor
                except Exception:
                    return 0.0
        try:
            return float(text)
        except Exception:
            return 0.0

    def pull_image(self):
        image = self.image_var.get().strip() or DEFAULT_IMAGE
        self.run_action(["docker", "pull", image], "Pull Image")

    def run_container(self, on_success=None, quiet=False):
        image = self.image_var.get().strip() or DEFAULT_IMAGE
        volume = self.volume_var.get().strip() or DEFAULT_VOLUME
        inspect_code, inspect_out, _ = run_command(
            ["docker", "inspect", CONTAINER_NAME, "--format", "{{.State.Running}}"]
        )
        if inspect_code == 0:
            if inspect_out.strip().lower() == "true":
                if not quiet:
                    self.ui_info(
                        "Run Container",
                        f"Container '{CONTAINER_NAME}' already exists and is running.",
                    )
                self.refresh_all()
                if on_success:
                    on_success()
                return
            self._run_in_background(
                ["docker", "start", CONTAINER_NAME],
                "Start Existing Container",
                refresh_after=True,
                timeout=None,
                on_success=on_success,
                quiet=quiet,
            )
            return

        cmd = [
            "docker",
            "run",
            "--name",
            CONTAINER_NAME,
            "-dit",
            "-v",
            f"{volume}:/data",
            image,
        ]
        self._run_in_background(
            cmd,
            "Run Container",
            refresh_after=True,
            timeout=None,
            on_success=on_success,
            quiet=quiet,
        )

    def start_container(self):
        self.run_action(["docker", "start", CONTAINER_NAME], "Start Container")

    def stop_container(self):
        self.run_action(["docker", "stop", CONTAINER_NAME], "Stop Container")

    def restart_container(self):
        self.run_action(["docker", "restart", CONTAINER_NAME], "Restart Container")

    def _open_terminal_with_command(self, inner_cmd: str):
        """Run a blocking command in a new terminal (Windows / macOS / Linux)."""
        if sys.platform == "win32":
            subprocess.Popen(
                ["powershell", "-NoExit", "-Command", inner_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        if sys.platform == "darwin":
            esc = inner_cmd.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.Popen(
                [
                    "osascript",
                    "-e",
                    f'tell application "Terminal" to do script "{esc}"',
                ]
            )
            return
        # Linux: try common terminal emulators
        for spec in (
            ["x-terminal-emulator", "-e", "sh", "-c", inner_cmd],
            ["gnome-terminal", "--", "sh", "-c", inner_cmd],
            ["konsole", "-e", "sh", "-c", inner_cmd],
            ["xfce4-terminal", "-e", f"sh -c {shlex.quote(inner_cmd)}"],
            ["xterm", "-e", inner_cmd],
        ):
            try:
                subprocess.Popen(spec)
                return
            except (FileNotFoundError, OSError):
                continue
        try:
            subprocess.Popen(["xterm", "-e", inner_cmd])
        except (FileNotFoundError, OSError):
            self.ui_warn(
                "Terminal",
                "No terminal emulator found. Run this in a terminal yourself:\n\n" + inner_cmd,
            )

    def open_shell(self):
        inner = f"docker exec -it -u {CONTAINER_USER} {CONTAINER_NAME} sh"
        self._open_terminal_with_command(inner)

    def follow_logs_external(self):
        # Opens real-time logs in a new terminal window.
        self._open_terminal_with_command(f"docker logs -f {CONTAINER_NAME}")

    def uninstall_node_setup(self):
        image = self.image_var.get().strip() or DEFAULT_IMAGE
        volume = self.volume_var.get().strip() or DEFAULT_VOLUME
        confirm = self.ui_confirm(
            "Uninstall Node Setup",
            "This removes local Edge Node runtime resources:\n"
            f"- Container: {CONTAINER_NAME}\n"
            f"- Image: {image}\n"
            f"- Volume: {volume}\n\n"
            "This deletes persisted node data in the selected volume.\n\nContinue?",
        )
        if not confirm:
            return

        self.action_status_var.set("Uninstall running...")

        def worker():
            commands = [
                (["docker", "rm", "-f", CONTAINER_NAME], "Remove container"),
                (["docker", "rmi", image], "Remove image"),
                (["docker", "volume", "rm", volume], "Remove volume"),
            ]
            results = []
            for cmd, label in commands:
                code, out, err = run_command(cmd, timeout=None)
                if code == 0:
                    results.append(f"[OK] {label}: {out or 'done'}")
                else:
                    results.append(f"[WARN] {label}: {err or out or 'skipped'}")

            def done():
                self.action_status_var.set("Idle")
                self.refresh_all()
                self.ui_info(
                    "Uninstall Complete",
                    "BroNode completed uninstall steps.\n\n" + "\n".join(results),
                )

            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def pick_config_tool(self):
        if sys.platform == "win32":
            ft = [("Executable", "*.exe"), ("All files", "*.*")]
        else:
            ft = [("Executable", "*"), ("All files", "*.*")]
        path = filedialog.askopenfilename(
            title="Select happ_config_file executable",
            filetypes=ft,
        )
        if path:
            self.config_tool_path_var.set(path)

    def pick_input_config(self):
        path = filedialog.askopenfilename(
            title="Select hApp config file",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.config_input_var.set(path)

    def pick_install_config(self):
        path = filedialog.askopenfilename(
            title="Select install config file",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.install_config_var.set(path)

    def on_catalog_selected(self, _event=None):
        if self._catalog_syncing:
            return
        selected = self.catalog_choice_var.get().strip()
        for item in APP_CATALOG:
            if item["label"] == selected:
                self.catalog_name_var.set(item["name"])
                self.catalog_version_var.set(item["version"])
                self.catalog_url_var.set(item["happ_url"])
                self.catalog_info_var.set(item["notes"])
                if self.catalog_tree:
                    for iid in self.catalog_tree.get_children():
                        vals = self.catalog_tree.item(iid, "values")
                        if vals and vals[0] == selected:
                            self._catalog_syncing = True
                            try:
                                self.catalog_tree.selection_set(iid)
                                self.catalog_tree.see(iid)
                            finally:
                                self._catalog_syncing = False
                            break
                return

    def _populate_catalog_tree(self):
        if not self.catalog_tree:
            return
        for row in self.catalog_tree.get_children():
            self.catalog_tree.delete(row)
        for item in APP_CATALOG:
            url = str(item.get("happ_url", "") or "").strip()
            hostable = "Yes" if (url.startswith(("http://", "https://")) and "example.com" not in url.lower()) else "No"
            self.catalog_tree.insert("", tk.END, values=(item["label"], hostable, url))

    def _on_catalog_tree_selected(self, _event=None):
        if self._catalog_syncing:
            return
        if not self.catalog_tree:
            return
        sel = self.catalog_tree.selection()
        if not sel:
            return
        vals = self.catalog_tree.item(sel[0], "values")
        if vals:
            self._catalog_syncing = True
            try:
                self.catalog_choice_var.set(vals[0])
                self.on_catalog_selected()
            finally:
                self._catalog_syncing = False

    def generate_catalog_config(self):
        app_name = (self.catalog_name_var.get().strip() or "my_happ").lower().replace(" ", "_")
        app_version = self.catalog_version_var.get().strip() or "0.1.0"
        happ_url = self.catalog_url_var.get().strip()
        if not happ_url:
            self.ui_error(
                "Generate Config",
                "Missing hApp URL.\n\nPaste a direct .happ/.webhapp release URL, then generate again.",
            )
            return
        network_seed = self.catalog_seed_var.get().strip()
        cfg = {
            "app": {
                "name": app_name,
                "version": app_version,
                "happUrl": happ_url,
                "modifiers": {"networkSeed": network_seed, "properties": {}},
            },
            "env": {"holochain": {"version": "", "flags": [""], "bootstrapUrl": ""}},
        }
        if self.config_iroh_var.get():
            cfg["env"]["holochain"]["relayUrl"] = ""
        else:
            cfg["env"]["holochain"]["signalServerUrl"] = ""
            cfg["env"]["holochain"]["stunServerUrls"] = [""]

        out_name = f"{app_name}_catalog_config.json"
        out_path = os.path.join(os.getcwd(), out_name)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
        self.config_input_var.set(out_path)
        self.install_config_var.set(out_path)
        self.ui_info(
            "Config Generated",
            f"Config created:\n{out_path}\n\nNext: open hApp Ops and click Install hApp.",
        )

    def use_catalog_in_ops(self):
        if not self.install_config_var.get().strip():
            self.ui_warn("Use In hApp Ops", "Generate a catalog config first.")
            return
        self.ui_info(
            "Use In hApp Ops",
            "Config file is set for install.\nOpen 'hApp Ops' and click 'Install hApp'.",
        )

    def host_selected_catalog_app(self):
        self.generate_catalog_config()
        if not self.install_config_var.get().strip():
            return
        self.goto_tab("hApp Ops")
        self.install_happ()

    def create_happ_config(self):
        tool = self.config_tool_path_var.get().strip()
        if not tool:
            self.ui_error(
                "Create Config",
                "happ_config_file CLI path is missing.\n\nSet CLI path first, then create config.",
            )
            return
        cmd = [tool, "create", "--name", self.config_name_var.get().strip() or "my_happ"]
        if self.config_iroh_var.get():
            cmd.append("--iroh")
        if self.config_gateway_var.get():
            cmd.append("--gateway")
        if self.config_economics_var.get():
            cmd.append("--economics")
        if self.config_init_zome_var.get():
            cmd.append("--init-zome-calls")
        self._run_in_background(cmd, "Create Config", refresh_after=False, timeout=None)

    def validate_happ_config(self):
        tool = self.config_tool_path_var.get().strip()
        config = self.config_input_var.get().strip()
        if not tool or not config:
            self.ui_error(
                "Validate Config",
                "Set both CLI path and input config file before validation.",
            )
            return
        cmd = [tool, "validate", "--input", config]
        self._run_in_background(cmd, "Validate Config", refresh_after=False, timeout=None)

    def _append_ops_output(self, text):
        if not self.show_raw_output_var.get():
            return
        if not self.ops_output_text:
            return
        self.ops_output_text.insert(tk.END, text + "\n")
        self.ops_output_text.see(tk.END)

    def _exec_in_container(self, args, title, on_success=None):
        cmd = docker_exec_base() + args
        self.action_status_var.set(f"{title} running...")

        def worker():
            code, out, err = run_command(cmd, timeout=None)

            def done():
                self.action_status_var.set("Idle")
                header = f"\n>>> {title}\n$ {' '.join(args)}\n"
                self._append_ops_output(header + (out or err or "(no output)"))
                if code != 0:
                    raw = err or out or "Command failed."
                    msg = format_docker_user_message(raw)
                    if raw == msg:
                        msg = raw + "\n\nTip: ensure container is running and admin port is correct."
                    self.ui_error(title, msg)
                elif on_success:
                    on_success()

            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def install_happ(self):
        cfg = self.install_config_var.get().strip()
        if not cfg:
            self.ui_error(
                "Install hApp",
                "No config file selected.\n\nChoose a JSON config in hApp Ops, then install.",
            )
            return
        if not os.path.exists(cfg):
            self.ui_error(
                "Install hApp",
                f"Config file not found:\n{cfg}\n\nSelect a valid local JSON file and retry.",
            )
            return

        # install_happ runs inside the container, so local Windows paths must be copied in first.
        container_cfg = f"/tmp/{os.path.basename(cfg)}"
        copy_code, copy_out, copy_err = run_command(
            ["docker", "cp", cfg, f"{CONTAINER_NAME}:{container_cfg}"],
            timeout=None,
        )
        if copy_code != 0:
            self.ui_error(
                "Install hApp",
                "Failed to copy config file into container.\n\n"
                + (copy_err or copy_out or "Unknown docker cp error"),
            )
            return

        # Config copied as root; install_happ runs as nonroot — must be readable.
        run_command(
            ["docker", "exec", CONTAINER_NAME, "chown", f"{CONTAINER_USER}:{CONTAINER_USER}", container_cfg],
            timeout=30,
        )

        args = ["install_happ", "-p", self.admin_port_var.get().strip() or "4444", container_cfg]
        node_name = self.node_name_var.get().strip()
        if node_name:
            args.append(node_name)
        self._exec_in_container(args, "Install hApp", on_success=self.list_happs)

    def list_happs(self):
        args = ["list_happs", "-p", self.admin_port_var.get().strip() or "4444"]
        cmd = docker_exec_base() + args
        self.action_status_var.set("List hApps running...")

        def worker():
            code, out, err = run_command(cmd, timeout=None)
            combined = "\n".join(x for x in (out, err) if x)

            def done():
                self.action_status_var.set("Idle")
                if self.show_raw_output_var.get():
                    header = f"\n>>> List hApps\n$ {' '.join(args)}\n"
                    self._append_ops_output(header + (combined or "(no output)"))
                if code != 0:
                    self.ui_error(
                        "List hApps",
                        (combined or "Command failed.")
                        + "\n\nTip: ensure container is running.",
                    )
                    return
                self._render_happs_table(combined)

            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _render_happs_table(self, text):
        if not self.apps_tree:
            return
        for row in self.apps_tree.get_children():
            self.apps_tree.delete(row)

        payload = text.strip()
        if not payload:
            self.apps_count_var.set("Installed apps: 0")
            self.apps_enabled_var.set("Enabled: 0")
            self.apps_last_var.set("Latest app: -")
            self.hosted_apps_list_cache = []
            return

        apps = parse_list_apps_json(payload)
        if apps is None:
            try:
                apps = json.loads(payload)
                if not isinstance(apps, list):
                    raise ValueError("Expected list")
            except Exception:
                self.apps_count_var.set("Installed apps: ?")
                self.apps_enabled_var.set("Enabled: ?")
                self.apps_last_var.set("Latest app: parse failed")
                preview = payload[:900] + ("…" if len(payload) > 900 else "")
                self.ui_warn(
                    "List hApps - parse error",
                    "Could not parse JSON from list-apps.\n\n"
                    "Turn on 'Show raw command output' and retry, or copy the raw output below.\n\n"
                    f"---\n{preview}",
                )
                self.hosted_apps_list_cache = []
                return

        self.hosted_apps_list_cache = apps
        enabled_count = 0
        latest = "-"
        hosted_lines = []
        for app in apps:
            app_id = app.get("installed_app_id", "-")
            latest = app_id or latest
            status_obj = app.get("status", {})
            status = status_obj.get("type", "-") if isinstance(status_obj, dict) else str(status_obj)
            if str(status).lower() == "enabled":
                enabled_count += 1
            version = "-"
            if "::" in app_id:
                parts = app_id.split("::")
                if len(parts) >= 2:
                    version = parts[1]
            installed_at = str(app.get("installed_at", "-"))
            self.apps_tree.insert("", tk.END, values=(app_id, status, version, installed_at))
            hosted_lines.append((app_id, status))

        self.apps_count_var.set(f"Installed apps: {len(apps)}")
        self.apps_enabled_var.set(f"Enabled: {enabled_count}")
        self.apps_last_var.set(f"Latest app: {latest if latest else '-'}")
        self._update_hosting_panel(hosted_lines)

    def on_happ_selected(self, _event=None):
        if not self.apps_tree:
            return
        selected = self.apps_tree.selection()
        if not selected:
            return
        values = self.apps_tree.item(selected[0], "values")
        if values:
            self.app_id_var.set(values[0])

    @staticmethod
    def _status_is_enabled(status):
        low = str(status or "").strip().lower()
        return low in ("enabled", "running") or "enabled" in low or "running" in low

    def _update_hosting_panel(self, hosted_lines):
        self.hosted_apps_cache = hosted_lines
        if not hosted_lines:
            self.hosted_apps_list_cache = []
        enabled = [line for line in hosted_lines if self._status_is_enabled(line[1])]
        self.hosting_title_var.set("Status")
        if not self.hosting_text:
            return
        self.hosting_text.configure(state=tk.NORMAL)
        self.hosting_text.delete("1.0", tk.END)
        self.hosting_text.insert(
            tk.END,
            (
                f"Container: {self.status_vars['Container'].get()}\n"
                f"Running: {self.status_vars['Running'].get()}\n"
                f"Docker: {self.status_vars['Docker'].get()}\n"
                f"Local IP: {self.status_vars['Local IP'].get()}\n"
                f"Status: {self.status_vars['Status'].get()}\n"
                f"Image: {self.status_vars['Image'].get()}\n"
                f"Started: {self.status_vars['StartedAt'].get()}\n"
                f"CPU: {self.stats_vars['CPU'].get()}\n"
                f"Memory: {self.stats_vars['Memory'].get()}\n"
                f"Net I/O: {self.stats_vars['NetIO'].get()}\n\n"
                f"Block I/O: {self.stats_vars['BlockIO'].get()}\n"
                f"PIDs: {self.stats_vars['PIDs'].get()}\n\n"
                f"Apps: {len(enabled)} enabled / {len(hosted_lines)} installed\n"
            ),
        )
        if hosted_lines:
            self.hosting_text.insert(tk.END, "\nRecent apps:\n")
            for app_id, status in hosted_lines[:5]:
                icon = "ON" if self._status_is_enabled(status) else "OFF"
                self.hosting_text.insert(tk.END, f"[{icon}] {app_id}\n")
        self.hosting_text.configure(state=tk.DISABLED)
        self.refresh_banner_text()

    def refresh_hosted_apps_if_due(self):
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        if now_ms - self.last_hosted_refresh_ms < 12000:
            return
        self.last_hosted_refresh_ms = now_ms
        if self.status_vars["Running"].get() != "Yes":
            self._update_hosting_panel([])
            return

        args = ["list_happs", "-p", self.admin_port_var.get().strip() or "4444"]
        cmd = docker_exec_base() + args

        def worker():
            code, out, err = run_command(cmd, timeout=20)
            combined = "\n".join(x for x in (out, err) if x)

            def done():
                if code != 0:
                    return
                payload = combined.strip()
                try:
                    apps = parse_list_apps_json(payload) if payload else []
                    if apps is None:
                        apps = json.loads(payload) if payload else []
                    if not isinstance(apps, list):
                        apps = []
                    hosted_lines = []
                    for app in apps:
                        app_id = app.get("installed_app_id", "-")
                        status_obj = app.get("status", {})
                        status = status_obj.get("type", "-") if isinstance(status_obj, dict) else str(status_obj)
                        hosted_lines.append((app_id, status))
                    self.hosted_apps_list_cache = apps
                    self._update_hosting_panel(hosted_lines)
                except Exception:
                    pass

            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def enable_happ(self):
        app_id = self.app_id_var.get().strip()
        if not app_id:
            self.ui_error("Enable hApp", "Provide an app ID from list_happs output.")
            return
        args = ["enable_happ", "-p", self.admin_port_var.get().strip() or "4444", app_id]
        self._exec_in_container(args, "Enable hApp", on_success=self.list_happs)

    def disable_happ(self):
        app_id = self.app_id_var.get().strip()
        if not app_id:
            self.ui_error("Disable hApp", "Provide an app ID from list_happs output.")
            return
        args = ["disable_happ", "-p", self.admin_port_var.get().strip() or "4444", app_id]
        self._exec_in_container(args, "Disable hApp", on_success=self.list_happs)

    def uninstall_happ(self):
        app_id = self.app_id_var.get().strip()
        if not app_id:
            self.ui_error("Uninstall hApp", "Provide an app ID from list_happs output.")
            return
        args = ["uninstall_happ", "-p", self.admin_port_var.get().strip() or "4444", app_id]
        self._exec_in_container(args, "Uninstall hApp", on_success=self.list_happs)

    def pick_backup_dir(self):
        path = filedialog.askdirectory(title="Choose backup output directory")
        if path:
            self.backup_dir_var.set(path)

    def pick_restore_file(self):
        path = filedialog.askopenfilename(
            title="Choose backup archive",
            filetypes=[("Tar GZip", "*.tar.gz"), ("All files", "*.*")],
        )
        if path:
            self.restore_file_var.set(path)

    def backup_volume(self):
        output_dir = self.backup_dir_var.get().strip()
        volume = self.volume_var.get().strip() or DEFAULT_VOLUME
        if not output_dir:
            self.ui_error("Create Backup", "Choose a backup output directory first.")
            return
        if not os.path.isdir(output_dir):
            self.ui_error("Create Backup", f"Backup directory does not exist:\n{output_dir}")
            return
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{APP_NAME.lower()}-{volume}-{ts}.tar.gz"
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume}:/data:ro",
            "-v",
            f"{output_dir}:/backup",
            "busybox",
            "tar",
            "czf",
            f"/backup/{filename}",
            "-C",
            "/data",
            ".",
        ]
        self._run_in_background(cmd, "Create Backup", refresh_after=False, timeout=None)

    def restore_volume(self):
        restore_file = self.restore_file_var.get().strip()
        volume = self.volume_var.get().strip() or DEFAULT_VOLUME
        if not restore_file:
            self.ui_error("Restore Backup", "Choose a backup archive first.")
            return
        if not os.path.isfile(restore_file):
            self.ui_error("Restore Backup", f"Backup archive not found:\n{restore_file}")
            return
        if not self.ui_confirm(
            "Restore Backup",
            "This will replace data in the Docker volume. Continue?",
        ):
            return
        restore_dir = os.path.dirname(restore_file)
        restore_name = os.path.basename(restore_file)
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume}:/data",
            "-v",
            f"{restore_dir}:/backup",
            "busybox",
            "sh",
            "-c",
            f"rm -rf /data/* /data/.[!.]* /data/..?* && tar xzf {shlex.quote('/backup/' + restore_name)} -C /data",
        ]
        self._run_in_background(cmd, "Restore Backup", refresh_after=True, timeout=None)

    def _load_mascot_photo(self, size=84):
        if not os.path.exists(MASCOT_SVG):
            return None
        png_path = os.path.join(tempfile.gettempdir(), f"bro_node_mascot_{size}.png")
        try:
            import cairosvg  # type: ignore

            cairosvg.svg2png(url=MASCOT_SVG, write_to=png_path, output_width=size, output_height=size)
            return tk.PhotoImage(file=png_path)
        except Exception:
            return None

    def _check_dependencies(self):
        python_ok = True
        cairosvg_ok = importlib.util.find_spec("cairosvg") is not None
        docker_code, _, _ = run_command(["docker", "ps"], timeout=15)
        docker_ok = docker_code == 0
        return {
            "python": python_ok,
            "docker": docker_ok,
            "cairosvg": cairosvg_ok,
        }

    def refresh_banner_text(self):
        hosted_names = [
            app_id.split("::")[0] if "::" in app_id else app_id
            for app_id, status in self.hosted_apps_cache
            if self._status_is_enabled(status)
        ]
        hosted_chunk = ", ".join(hosted_names[:3]) if hosted_names else "none"
        parts = [
            f"LOCAL_IP={self.status_vars['Local IP'].get()}",
            f"DOCKER={self.status_vars['Docker'].get()}",
            f"CONTAINER={self.status_vars['Container'].get()}",
            f"RUNNING={self.status_vars['Running'].get()}",
            f"STATUS={self.status_vars['Status'].get()}",
            f"ENABLED_APPS={hosted_chunk}",
            f"CPU={self.stats_vars['CPU'].get()}",
            f"MEM={self.stats_vars['Memory'].get()}",
            f"NET={self.stats_vars['NetIO'].get()}",
            f"APP_ACTION={self.action_status_var.get()}",
        ]
        self.banner_text = "  //  ".join(parts) + "  //  "
        if self.banner_text != self.banner_last_text:
            self.banner_last_text = self.banner_text
            self._reset_banner_item()

    def _banner_speed_params(self):
        """Pixels moved per frame and delay until next frame (slider 1=slow … 100=fast)."""
        try:
            v = int(self.banner_speed_var.get())
        except (TypeError, ValueError, tk.TclError):
            v = 50
        v = max(1, min(100, v))
        t = (v - 1) / 99.0
        delta = 0.35 + t * 2.35
        interval_ms = int(round(28 - t * 18))
        interval_ms = max(8, min(32, interval_ms))
        return delta, interval_ms

    def start_banner_loop(self):
        if not self.banner_text:
            self.refresh_banner_text()
        self._animate_banner()
        _, interval_ms = self._banner_speed_params()
        self.root.after(interval_ms, self.start_banner_loop)

    def _on_banner_resize(self, _event):
        self._reset_banner_item()

    def _reset_banner_item(self):
        if not self.banner_canvas:
            return
        canvas = self.banner_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        self.banner_x = width + 10
        self.banner_item = canvas.create_text(
            self.banner_x,
            15,
            text=self.banner_text or "BRO NODE // booting...",
            fill=UI_ACCENT_DIM,
            anchor="w",
            font=FONT_MONO,
        )

    def _animate_banner(self):
        if not self.banner_canvas:
            return
        canvas = self.banner_canvas
        if self.banner_item is None:
            self._reset_banner_item()
            return

        delta, _ = self._banner_speed_params()
        canvas.move(self.banner_item, -delta, 0)
        bbox = canvas.bbox(self.banner_item)
        if not bbox:
            return
        _, _, x2, _ = bbox
        if x2 < 0:
            width = max(1, canvas.winfo_width())
            canvas.coords(self.banner_item, width + 10, 15)

    def _draw_dependency_status(self, status):
        if not self.dep_canvas:
            return
        c = self.dep_canvas
        c.delete("all")
        labels = [
            ("Python", status.get("python", False)),
            ("Docker", status.get("docker", False)),
            ("Mascot", status.get("cairosvg", False)),
        ]
        x = 6
        y = 17
        for label, ok in labels:
            color = UI_ACCENT if ok else UI_GRID
            c.create_oval(x, y - 6, x + 12, y + 6, fill=color, outline=UI_BORDER if ok else "")
            x += 18
            text_color = UI_ACCENT_DIM if ok else UI_TEXT_MUTE
            c.create_text(x, y, text=label, fill=text_color, anchor="w", font=FONT_MONO_SM)
            x += 58

        core_ok = status.get("python") and status.get("docker")
        # From source, cairosvg is optional (same as frozen builds) so Docker alone unlocks the UI.
        app_ready = core_ok
        if app_ready:
            if not status.get("cairosvg"):
                if _is_frozen():
                    self.dep_status_var.set("Ready (mascot optional in packaged build)")
                else:
                    self.dep_status_var.set("Ready (pip install cairosvg for header mascot)")
            else:
                self.dep_status_var.set("All dependencies ready")
            self.dep_action_var.set("Ready")
            if self.dep_action_button is not None:
                self.dep_action_button.state(["disabled"])
        else:
            missing = [k for k, ok in status.items() if not ok]
            self.dep_status_var.set("Waiting: " + ", ".join(missing))
            if "docker" in missing:
                self.dep_action_var.set("Open Docker")
            elif "cairosvg" in missing and not _is_frozen():
                self.dep_action_var.set("Install Mascot Dependency")
            else:
                self.dep_action_var.set("Retry")
            if self.dep_action_button is not None:
                self.dep_action_button.state(["!disabled"])

    def ensure_dependencies_and_continue(self):
        status = self._check_dependencies()
        self._draw_dependency_status(status)

        # Do not block on mascot: frozen builds may omit cairosvg; from source it is optional too.
        self.dependencies_ready = status.get("python") and status.get("docker")
        if self.dependencies_ready:
            if not self.bootstrap_complete:
                self.ensure_image_ready_then_continue()
                return
            self.refresh_all()
        else:
            self.root.after(3000, self.ensure_dependencies_and_continue)

    def ensure_image_ready_then_continue(self):
        """Do not block startup on image pull; Start Here wizard guides pull → container."""
        self.bootstrap_complete = True
        self.refresh_all()

    def pull_image_with_progress(self, image, on_complete=None):
        dlg = tk.Toplevel(self.root)
        dlg.withdraw()
        dlg.title("Pulling Edge Node Image")
        dlg.configure(bg=UI_BG)
        dlg.transient(self.root)
        dlg.resizable(False, False)

        status_var = tk.StringVar(value=f"Pulling {image}")
        detail_var = tk.StringVar(value="Initializing...")

        ttk.Label(dlg, textvariable=status_var, style="Header.TLabel").pack(anchor="w", padx=16, pady=(14, 6))
        ttk.Label(
            dlg,
            text="Docker is downloading the Edge Node image from the registry. Large images can take several minutes; the line below shows the latest progress from Docker.",
            style="Subtle.TLabel",
            wraplength=520,
        ).pack(anchor="w", padx=16, pady=(0, 6))
        ttk.Label(dlg, textvariable=detail_var, style="Subtle.TLabel").pack(anchor="w", padx=16, pady=(0, 10))

        progress = ttk.Progressbar(dlg, mode="indeterminate", length=520)
        progress.pack(padx=16, pady=(0, 12))
        progress.start(12)

        ttk.Label(
            dlg,
            text="Please wait until this window closes on its own. Do not quit BroNode while the pull is running.",
            style="Subtle.TLabel",
            wraplength=520,
        ).pack(anchor="w", padx=16, pady=(0, 8))

        self._center_toplevel(dlg, min_w=560, min_h=240)
        dlg.deiconify()
        dlg.lift(self.root)
        dlg.update_idletasks()
        dlg.focus_set()

        self.action_status_var.set("Pull Image running...")

        def worker():
            try:
                pull_cmd = _normalize_subprocess_argv(["docker", "pull", image])
                proc = subprocess.Popen(
                    pull_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    stdin=subprocess.DEVNULL,
                    **_subprocess_no_console_kwargs(),
                )
                last_line = "Downloading layers..."
                for line in proc.stdout:
                    cleaned = line.strip()
                    if cleaned:
                        last_line = cleaned
                        self.root.after(0, lambda t=last_line: detail_var.set(t[:150]))
                exit_code = proc.wait()
                success = exit_code == 0
                self.root.after(
                    0,
                    lambda: self._on_pull_complete(
                        dlg, progress, success, last_line, on_complete
                    ),
                )
            except Exception as exc:
                self.root.after(
                    0,
                    lambda: self._on_pull_complete(
                        dlg, progress, False, f"Pull failed: {exc}", on_complete
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_pull_complete(self, dialog, progress, success, message, on_complete=None):
        progress.stop()
        dialog.destroy()
        if on_complete:
            self.action_status_var.set("Idle")
            if success:
                self.bootstrap_complete = True

            def invoke():
                on_complete(success, message or "")

            self.root.after(0, invoke)
            return
        if success:
            self.action_status_var.set("Idle")
            self.bootstrap_complete = True
            self.ui_info(
                "Image Pull Complete",
                "Edge Node image pulled successfully.\n\nNext: use Tools -> Run Container.",
            )
            self.refresh_all()
        else:
            self.action_status_var.set("Idle")
            self.ui_error(
                "Image Pull Failed",
                (message or "Unable to pull image.")
                + "\n\nTip: verify internet access, Docker login, and image name.",
            )
            # Keep bootstrap incomplete and retry dependency/bootstrap checks.
            self.root.after(1500, self.ensure_dependencies_and_continue)

    def _open_docker_application(self):
        if sys.platform == "win32":
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    "Start-Process 'Docker Desktop'",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **_subprocess_no_console_kwargs(),
            )
            return
        if sys.platform == "darwin":
            try:
                subprocess.Popen(["open", "-a", "Docker"])
                return
            except (FileNotFoundError, OSError):
                pass
            self.ui_warn(
                "Docker",
                "Install Docker Desktop for Mac from docker.com and start it, then click Retry.",
            )
            return
        self.ui_warn(
            "Docker",
            "Start Docker on Linux:\n"
            "• Docker Desktop: open it from your app menu, or\n"
            "• Docker Engine: sudo systemctl start docker (and add your user to the docker group).\n\n"
            "Then click Retry in BroNode.",
        )

    def handle_dependency_action(self):
        status = self._check_dependencies()
        if not status.get("docker"):
            self._open_docker_application()
            return
        if not status.get("cairosvg"):
            if _is_frozen():
                self.ui_warn(
                    "Mascot dependency",
                    "cairosvg is not available in this frozen build (or Cairo failed to load).\n\n"
                    "The app still runs; the header mascot may be missing. Reinstall from a build that bundles cairosvg, or run from source with: python -m pip install cairosvg",
                )
                return
            self._run_in_background(
                [sys.executable, "-m", "pip", "install", "cairosvg"],
                "Install Dependency",
                refresh_after=False,
                timeout=None,
            )
            self.root.after(1500, self.ensure_dependencies_and_continue)
            return
        self.ensure_dependencies_and_continue()


if __name__ == "__main__":
    root = tk.Tk()
    app = EdgeNodeGui(root)
    root.mainloop()
