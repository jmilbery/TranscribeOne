#!/usr/bin/env python3

"""
TranscribeOne GUI
-----------------
macOS desktop application for transcribing audio files with speaker
identification using AssemblyAI.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------------------------------------------------------------------
# Deferred imports — availability checks only
# ---------------------------------------------------------------------------
# Heavy libraries (pygame, assemblyai/transcribeone, anthropic) are NOT
# imported at module level.  In a PyInstaller .app bundle on macOS,
# Gatekeeper scans every .dylib/.so on first load, making these imports
# take 10-30+ seconds.  Instead we use lightweight find_spec() checks
# here and defer the actual imports to background threads / first use.

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

HAS_AUDIO = importlib.util.find_spec("pygame") is not None
HAS_TRANSCRIBE = importlib.util.find_spec("transcribeone") is not None
HAS_SHOW_NOTES = (
    importlib.util.find_spec("anthropic") is not None
    and importlib.util.find_spec("show_notes_processor") is not None
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME = "TranscribeOne"
CONFIG_DIR = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
KEYCHAIN_SERVICE = "TranscribeOne"
KEYCHAIN_ACCOUNT = "api_key"
KEYCHAIN_ANTHROPIC = "anthropic_api_key"
WINDOW_WIDTH = 720
WINDOW_HEIGHT = 850

# Supported audio formats (duplicated from transcribeone.py to avoid
# importing the heavy assemblyai library at module level).
SUPPORTED_FORMATS = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".webm")

AUDIO_FILETYPES = [
    ("Audio files", " ".join(f"*{ext}" for ext in SUPPORTED_FORMATS)),
    ("All files", "*.*"),
]
SPEED_OPTIONS = ["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"]
DEFAULT_SPEED = "1.0x"

# Video formats that can be converted to audio via ffmpeg
VIDEO_FORMATS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v")

# Color palette
CLR_BG = "#f5f5f7"             # Window background
CLR_ACCENT = "#0071e3"         # Primary accent (Apple blue)
CLR_ACCENT_HOVER = "#0077ED"
CLR_SECTION_BG = "#ffffff"     # Section card background
CLR_SECTION_BD = "#d2d2d7"     # Section card border
CLR_TEXT = "#1d1d1f"           # Primary text
CLR_TEXT_SEC = "#86868b"       # Secondary text
CLR_SUCCESS = "#34c759"        # Success green
CLR_ERROR = "#ff3b30"          # Error red
CLR_HEADER = "#1d1d1f"        # Section header text
CLR_BTN_BG = "#e8e8ed"        # Button background
CLR_BTN_FG = "#1d1d1f"        # Button foreground
CLR_BTN_ACTIVE = "#d1d1d6"    # Button active/pressed


# ---------------------------------------------------------------------------
# ffmpeg helpers
# ---------------------------------------------------------------------------

def find_ffmpeg() -> str:
    """Return the path to ffmpeg if available, else empty string."""
    path = shutil.which("ffmpeg")
    return path or ""


HAS_FFMPEG = bool(find_ffmpeg())


def convert_video_to_audio(video_path: str, progress_callback=None) -> str:
    """Convert a video file to a temporary WAV audio file using ffmpeg.

    Returns the path to the temporary audio file.
    Raises RuntimeError on failure.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is not installed. Install it with: brew install ffmpeg")

    # Create temp file in the same directory as the video so auto-save
    # path stays sensible
    base = os.path.splitext(video_path)[0]
    tmp_audio = f"{base}_audio_tmp.wav"

    cmd = [
        ffmpeg, "-i", video_path,
        "-vn",                   # No video
        "-acodec", "pcm_s16le",  # Standard WAV
        "-ar", "44100",          # 44.1 kHz
        "-ac", "1",              # Mono (smaller, fine for speech)
        "-y",                    # Overwrite if exists
        tmp_audio,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed:\n{result.stderr[:500]}")

    return tmp_audio


# ---------------------------------------------------------------------------
# Keychain helpers (macOS-specific, uses `security` CLI)
# ---------------------------------------------------------------------------

def save_to_keychain(value: str, account: str = KEYCHAIN_ACCOUNT) -> bool:
    """Store a value in the macOS Keychain. Returns True on success.

    *account* distinguishes different keys (e.g. ``"api_key"`` for
    AssemblyAI, ``"anthropic_api_key"`` for Anthropic).
    """
    subprocess.run(
        ["security", "delete-generic-password",
         "-s", KEYCHAIN_SERVICE, "-a", account],
        capture_output=True,
    )
    result = subprocess.run(
        ["security", "add-generic-password",
         "-s", KEYCHAIN_SERVICE, "-a", account,
         "-w", value],
        capture_output=True,
    )
    return result.returncode == 0


def load_from_keychain(account: str = KEYCHAIN_ACCOUNT) -> str:
    """Retrieve a value from the macOS Keychain. Returns empty string if not found."""
    result = subprocess.run(
        ["security", "find-generic-password",
         "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return ""


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load app config from disk."""
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(config: dict) -> None:
    """Save app config to disk."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


# ---------------------------------------------------------------------------
# GUI Application
# ---------------------------------------------------------------------------

class TranscribeOneApp:
    """Main application window."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(520, 700)
        self.root.configure(bg=CLR_BG)

        # State
        self._api_key_var = tk.StringVar()
        self._audio_path_var = tk.StringVar()
        self._status_var = tk.StringVar(value="Ready")
        self._remember_key_var = tk.BooleanVar(value=False)
        self._transcribing = False
        self._show_key = False
        self._tmp_audio_file: str = ""  # temp file from video conversion

        # Audio player state
        self._playing = False
        self._paused = False
        self._speed_var = tk.StringVar(value=DEFAULT_SPEED)
        self._position_var = tk.DoubleVar(value=0.0)
        self._duration = 0.0
        self._position_update_id = None
        self._loaded_audio_path = None

        # Transcript state
        self._current_audio_file: str = ""
        self._raw_results: list[tuple[str, str]] = []
        self._speaker_name_vars: dict[str, tk.StringVar] = {}

        # Show Notes Generator state
        self._anthropic_key_var = tk.StringVar()
        self._show_anthropic_key = False
        self._remember_anthropic_key_var = tk.BooleanVar(value=False)
        self._generating_notes = False

        # API key verification state
        self._verifying_assemblyai = False
        self._verifying_anthropic = False

        # Deferred-import tracking.  Heavy libs are pre-loaded in a
        # background thread right after the window appears.  If the user
        # clicks an action before loading finishes, an overlay spinner is
        # shown until the import completes, then the action runs.
        self._libs_ready = False          # True once bg pre-import finishes
        self._pending_action = None       # callback queued while overlay is up
        self._overlay = None              # the overlay Frame, if visible

        # Clear verification feedback when key values change
        self._api_key_var.trace_add("write", self._on_assemblyai_key_changed)
        self._anthropic_key_var.trace_add("write", self._on_anthropic_key_changed)

        self._setup_styles()
        self._build_ui()
        self._setup_mac_open_document()
        self._load_preferences()

        # After all widgets are packed, schedule a one-time scroll-region
        # update. (No per-widget mousewheel binding needed — the Tcl-level
        # handler set up in _setup_tcl_mousewheel() covers everything.)
        self.root.after_idle(self._update_scroll_region)

        # Start pre-importing heavy libs in a background thread so they
        # are usually cached by the time the user clicks anything.
        threading.Thread(target=self._preload_libs, daemon=True).start()

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _setup_styles(self) -> None:
        """Configure ttk styles for a polished macOS-native appearance."""
        style = ttk.Style()
        style.theme_use("aqua")

        # Section card frames
        style.configure("Card.TFrame", background=CLR_SECTION_BG)

        # Section header labels
        style.configure(
            "SectionHeader.TLabel",
            background=CLR_SECTION_BG,
            foreground=CLR_HEADER,
            font=("SF Pro Display", 13, "bold"),
        )

        # Section icon labels
        style.configure(
            "SectionIcon.TLabel",
            background=CLR_SECTION_BG,
            foreground=CLR_ACCENT,
            font=("Helvetica", 16),
        )

        # Regular labels inside sections
        style.configure("Card.TLabel", background=CLR_SECTION_BG, foreground=CLR_TEXT)
        style.configure("CardMuted.TLabel", background=CLR_SECTION_BG, foreground=CLR_TEXT_SEC)

        # Status bar
        style.configure("Status.TLabel", background=CLR_BG, foreground=CLR_TEXT_SEC)
        style.configure("Status.TFrame", background=CLR_BG)

    # ------------------------------------------------------------------
    # Button factory (uses tk.Button for reliable macOS click handling)
    # ------------------------------------------------------------------

    @staticmethod
    def _make_button(parent, text: str, command,
                     width: int = 0, **kwargs) -> tk.Button:
        """Create a styled tk.Button.

        ttk.Button with the macOS aqua theme has unreliable mouse-click
        handling — clicks are often swallowed by focus changes.  Plain
        tk.Button does not have this problem.
        """
        opts: dict = {
            "text": text,
            "command": command,
            "font": ("SF Pro Text", 12),
            "relief": "raised",
            "bd": 1,
            "padx": 10,
            "pady": 3,
            "bg": CLR_BTN_BG,
            "fg": CLR_BTN_FG,
            "activebackground": CLR_BTN_ACTIVE,
            "activeforeground": CLR_BTN_FG,
        }
        if width:
            opts["width"] = width
        opts.update(kwargs)
        return tk.Button(parent, **opts)

    # ------------------------------------------------------------------
    # UI construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_section(parent, icon: str, title: str, **pack_kwargs) -> tk.Frame:
        """Create a visually distinct section card with icon and title.

        Returns the content frame to pack widgets into.
        """
        # Outer wrapper provides the rounded-corner card look
        outer = tk.Frame(parent, bg=CLR_SECTION_BD, bd=0, highlightthickness=0)
        pack_opts = {"fill": "x", "padx": 14, "pady": 3}
        pack_opts.update(pack_kwargs)
        outer.pack(**pack_opts)

        inner = tk.Frame(outer, bg=CLR_SECTION_BG, bd=0, highlightthickness=0)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        # Header row with icon + title
        header = ttk.Frame(inner, style="Card.TFrame")
        header.pack(fill="x", padx=10, pady=(6, 2))

        ttk.Label(header, text=icon, style="SectionIcon.TLabel").pack(side="left", padx=(0, 6))
        ttk.Label(header, text=title, style="SectionHeader.TLabel").pack(side="left")

        # Content area
        content = ttk.Frame(inner, style="Card.TFrame")
        content.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        return content

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct all widgets."""

        # --- Fixed Status Bar (always visible at bottom of window) ---
        self._status_bar = tk.Frame(self.root, bg="#e8e8ea", highlightthickness=0)
        self._status_bar.pack(side="bottom", fill="x")

        _sep = tk.Frame(self._status_bar, bg="#d1d1d6", height=1)
        _sep.pack(fill="x", side="top")

        _sb_inner = tk.Frame(self._status_bar, bg="#e8e8ea")
        _sb_inner.pack(fill="x", padx=14, pady=(4, 6))

        self._status_label = tk.Label(
            _sb_inner, textvariable=self._status_var,
            font=("SF Pro Text", 11), fg=CLR_TEXT_SEC, bg="#e8e8ea",
            anchor="w",
        )
        self._status_label.pack(side="left")

        self._progress = ttk.Progressbar(_sb_inner, mode="indeterminate", length=200)
        self._progress.pack(side="right")

        # --- Scrollable container ---
        # Wrap all content in a canvas so the window scrolls when
        # content exceeds the visible area (especially with the Show
        # Notes Generator section at the bottom).
        self._canvas = tk.Canvas(self.root, bg=CLR_BG, highlightthickness=0, takefocus=0)
        self._vscroll = ttk.Scrollbar(self.root, orient="vertical",
                                       command=self._canvas.yview)
        self._scroll_frame = tk.Frame(self._canvas, bg=CLR_BG)

        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._scroll_frame, anchor="nw",
        )
        self._canvas.configure(yscrollcommand=self._vscroll.set)

        self._vscroll.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # Keep the inner frame width matched to the canvas width.
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Mousewheel scrolling via a single Tcl-level binding.
        # This avoids the Python/Tcl bridge overhead that makes
        # buttons feel sluggish when hundreds of Python callbacks fire
        # per second from macOS trackpad scroll events.
        self._setup_tcl_mousewheel()

        # --- App Title Bar ---
        title_frame = tk.Frame(self._scroll_frame, bg=CLR_BG)
        title_frame.pack(fill="x", padx=14, pady=(8, 2))

        title_lbl = tk.Label(
            title_frame, text="TranscribeOne",
            font=("SF Pro Display", 20, "bold"),
            fg=CLR_TEXT, bg=CLR_BG,
        )
        title_lbl.pack(side="left")

        subtitle_lbl = tk.Label(
            title_frame, text="Audio Transcription with Speaker Labels",
            font=("SF Pro Text", 11),
            fg=CLR_TEXT_SEC, bg=CLR_BG,
        )
        subtitle_lbl.pack(side="left", padx=(10, 0), pady=(6, 0))

        # --- API Keys ---
        key_content = self._create_section(self._scroll_frame, "\U0001F511", "API Keys")

        # AssemblyAI key row
        ttk.Label(key_content, text="AssemblyAI:", style="Card.TLabel").pack(anchor="w", pady=(0, 2))

        aai_row = ttk.Frame(key_content, style="Card.TFrame")
        aai_row.pack(fill="x")

        self._api_key_entry = ttk.Entry(aai_row, textvariable=self._api_key_var, show="*", width=40)
        self._api_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._toggle_btn = self._make_button(aai_row, text="Show", command=self._toggle_api_key_visibility, width=6)
        self._toggle_btn.pack(side="left", padx=(0, 4))

        ttk.Checkbutton(aai_row, text="Remember", variable=self._remember_key_var).pack(side="left", padx=(0, 4))

        self._verify_aai_btn = self._make_button(aai_row, text="Verify", command=self._verify_assemblyai_key, width=6)
        self._verify_aai_btn.pack(side="left")

        self._aai_verify_label = ttk.Label(key_content, text="", style="CardMuted.TLabel")
        self._aai_verify_label.pack(anchor="w", pady=(2, 0))

        # Anthropic key row (only when show_notes_processor is available)
        if HAS_SHOW_NOTES:
            ttk.Label(key_content, text="Anthropic:", style="Card.TLabel").pack(anchor="w", pady=(6, 2))

            anthropic_row = ttk.Frame(key_content, style="Card.TFrame")
            anthropic_row.pack(fill="x")

            self._anthropic_key_entry = ttk.Entry(
                anthropic_row, textvariable=self._anthropic_key_var, show="*", width=40,
            )
            self._anthropic_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

            self._anthropic_toggle_btn = self._make_button(
                anthropic_row, text="Show",
                command=self._toggle_anthropic_key_visibility, width=6,
            )
            self._anthropic_toggle_btn.pack(side="left", padx=(0, 4))

            ttk.Checkbutton(
                anthropic_row, text="Remember",
                variable=self._remember_anthropic_key_var,
            ).pack(side="left", padx=(0, 4))

            self._verify_anthropic_btn = self._make_button(
                anthropic_row, text="Verify",
                command=self._verify_anthropic_key, width=6,
            )
            self._verify_anthropic_btn.pack(side="left")

            self._anthropic_verify_label = ttk.Label(key_content, text="", style="CardMuted.TLabel")
            self._anthropic_verify_label.pack(anchor="w", pady=(2, 0))

        # --- Source Media ---
        media_title = "Source Media" if HAS_FFMPEG else "Audio File"
        file_content = self._create_section(self._scroll_frame, "\U0001F3B5", media_title)

        path_row = ttk.Frame(file_content, style="Card.TFrame")
        path_row.pack(fill="x")

        self._path_entry = ttk.Entry(path_row, textvariable=self._audio_path_var, state="readonly", takefocus=False)
        self._path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._make_button(path_row, text="Browse\u2026", command=self._browse_file).pack(side="left")

        fmt_list = ", ".join(ext.lstrip(".") for ext in SUPPORTED_FORMATS)
        if HAS_FFMPEG:
            fmt_list += "  |  Video: " + ", ".join(ext.lstrip(".") for ext in VIDEO_FORMATS)
        fmt_label = ttk.Label(file_content, text=f"Supported: {fmt_list}", style="CardMuted.TLabel")
        fmt_label.pack(anchor="w", pady=(4, 0))

        if HAS_FFMPEG:
            ttk.Label(
                file_content,
                text="\u2713 ffmpeg detected \u2014 video files will be auto-converted",
                style="CardMuted.TLabel",
            ).pack(anchor="w", pady=(2, 0))

        # --- Audio Player ---
        player_content = self._create_section(self._scroll_frame, "\U0001F50A", "Player")

        controls_row = ttk.Frame(player_content, style="Card.TFrame")
        controls_row.pack(fill="x")

        self._play_btn = self._make_button(controls_row, text="\u25B6 Play", command=self._toggle_playback, width=8)
        self._play_btn.pack(side="left", padx=(0, 6))

        self._stop_btn = self._make_button(controls_row, text="\u25A0 Stop", command=self._stop_playback, width=8)
        self._stop_btn.pack(side="left", padx=(0, 12))

        ttk.Label(controls_row, text="Speed:", style="Card.TLabel").pack(side="left", padx=(0, 4))
        self._speed_combo = ttk.Combobox(
            controls_row, textvariable=self._speed_var,
            values=SPEED_OPTIONS, width=5, state="readonly",
            takefocus=False,
        )
        self._speed_combo.pack(side="left")
        self._speed_combo.bind("<<ComboboxSelected>>", self._on_speed_change)

        self._time_label = ttk.Label(controls_row, text="0:00 / 0:00", style="Card.TLabel")
        self._time_label.pack(side="right")

        # Seek bar
        self._seek_bar = ttk.Scale(
            player_content, from_=0, to=100, orient="horizontal",
            variable=self._position_var, command=self._on_seek,
        )
        self._seek_bar.pack(fill="x", pady=(6, 0))

        if not HAS_AUDIO:
            self._play_btn.configure(state="disabled")
            self._stop_btn.configure(state="disabled")
            self._speed_combo.configure(state="disabled")
            ttk.Label(player_content, text="Audio playback unavailable (pygame not installed)", foreground="#cc0000").pack(anchor="w")

        # --- Output Directory ---
        outdir_content = self._create_section(self._scroll_frame, "\U0001F4C2", "Output Directory")

        outdir_row = ttk.Frame(outdir_content, style="Card.TFrame")
        outdir_row.pack(fill="x")

        self._output_dir_var = tk.StringVar()
        self._outdir_entry = ttk.Entry(outdir_row, textvariable=self._output_dir_var, state="readonly", takefocus=False)
        self._outdir_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._make_button(outdir_row, text="Choose\u2026", command=self._browse_output_dir).pack(side="left")

        ttk.Label(
            outdir_content,
            text="Transcripts auto-save here (defaults to same folder as source file)",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        # --- Speaker Names ---
        names_content = self._create_section(self._scroll_frame, "\U0001F465", "Speaker Names (optional)")

        self._speaker_names_var = tk.StringVar()
        names_entry = ttk.Entry(names_content, textvariable=self._speaker_names_var)
        names_entry.pack(fill="x")

        ttk.Label(
            names_content,
            text="Enter expected speaker names separated by commas (e.g. Alice, Bob)",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        # --- Transcribe ---
        ctrl_frame = tk.Frame(self._scroll_frame, bg=CLR_BG)
        ctrl_frame.pack(fill="x", padx=14, pady=(3, 1))

        self._transcribe_btn = self._make_button(
            ctrl_frame, text="\u25B6  Transcribe",
            command=self._start_transcription,
            font=("SF Pro Text", 13, "bold"),
        )
        self._transcribe_btn.pack(side="right")

        # --- Speaker Rename (shown after transcription if API identification failed) ---
        self._rename_outer = tk.Frame(self._scroll_frame, bg=CLR_SECTION_BD, bd=0, highlightthickness=0)
        # Not packed yet — shown only when needed
        self._rename_inner_card = tk.Frame(self._rename_outer, bg=CLR_SECTION_BG, bd=0, highlightthickness=0)
        self._rename_inner_card.pack(fill="both", expand=True, padx=1, pady=1)

        rename_header = ttk.Frame(self._rename_inner_card, style="Card.TFrame")
        rename_header.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(rename_header, text="\u270F\uFE0F", style="SectionIcon.TLabel").pack(side="left", padx=(0, 6))
        ttk.Label(rename_header, text="Rename Speakers", style="SectionHeader.TLabel").pack(side="left")

        self._rename_content = ttk.Frame(self._rename_inner_card, style="Card.TFrame")
        self._rename_content.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._rename_inner = ttk.Frame(self._rename_content, style="Card.TFrame")
        self._rename_inner.pack(fill="x")

        self._apply_names_btn = self._make_button(
            self._rename_content, text="Apply Names",
            command=self._apply_speaker_names,
        )

        # --- Results ---
        result_outer = tk.Frame(self._scroll_frame, bg=CLR_SECTION_BD, bd=0, highlightthickness=0)
        result_outer.pack(fill="x", padx=14, pady=5)

        result_inner = tk.Frame(result_outer, bg=CLR_SECTION_BG, bd=0, highlightthickness=0)
        result_inner.pack(fill="both", expand=True, padx=1, pady=1)

        result_header = ttk.Frame(result_inner, style="Card.TFrame")
        result_header.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(result_header, text="\U0001F4DD", style="SectionIcon.TLabel").pack(side="left", padx=(0, 6))
        ttk.Label(result_header, text="Transcript", style="SectionHeader.TLabel").pack(side="left")

        self._result_frame = ttk.Frame(result_inner, style="Card.TFrame")
        self._result_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        text_frame = ttk.Frame(self._result_frame, style="Card.TFrame")
        text_frame.pack(fill="both", expand=True)

        self._result_text = tk.Text(
            text_frame, wrap="word", state="disabled",
            font=("Menlo", 12), bg="#fafafa", fg=CLR_TEXT,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=CLR_SECTION_BD,
            insertbackground=CLR_TEXT,
            height=15,
        )
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self._result_text.yview)
        self._result_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._result_text.pack(side="left", fill="both", expand=True)

        btn_row = ttk.Frame(self._result_frame, style="Card.TFrame")
        btn_row.pack(fill="x", pady=(6, 0))

        self._copy_btn = self._make_button(btn_row, text="Copy to Clipboard", command=self._copy_to_clipboard, state="disabled")
        self._copy_btn.pack(side="left", padx=(0, 6))

        self._save_btn = self._make_button(btn_row, text="Save As\u2026", command=self._save_to_file, state="disabled")
        self._save_btn.pack(side="left")

        self._output_path_label = ttk.Label(btn_row, text="", style="CardMuted.TLabel")
        self._output_path_label.pack(side="right")

        # --- Show Notes Generator ---
        if HAS_SHOW_NOTES:
            notes_content = self._create_section(
                self._scroll_frame, "\U0001F4DD", "Show Notes Generator"
            )

            # Generate button + status
            gen_row = tk.Frame(notes_content, bg=CLR_SECTION_BG)
            gen_row.pack(fill="x")

            self._generate_btn = self._make_button(
                gen_row, text="\u2728  Generate Show Notes",
                command=self._start_show_notes,
                font=("SF Pro Text", 13, "bold"),
            )
            self._generate_btn.pack(side="right")

            # Output info
            self._notes_output_label = ttk.Label(
                notes_content, text="", style="CardMuted.TLabel", wraplength=600,
            )
            self._notes_output_label.pack(anchor="w", pady=(4, 0))

        # Bottom spacer so the last section isn't flush with the window edge
        tk.Frame(self._scroll_frame, bg=CLR_BG, height=20).pack(fill="x")

    # ------------------------------------------------------------------
    # Scrollable container helpers
    # ------------------------------------------------------------------

    def _update_scroll_region(self) -> None:
        """Recalculate the canvas scroll region after layout changes.

        Called explicitly after UI build and content changes instead of
        via a <Configure> binding (which on macOS fires hundreds of times
        at startup and blocks the event loop).
        """
        self._scroll_frame.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        """Keep the inner frame width matched to the canvas."""
        self._canvas.itemconfig(self._canvas_window, width=event.width)
        # Also refresh scroll region since the available area changed.
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    # --- Mousewheel scrolling (single Tcl-level handler) ---------------

    def _setup_tcl_mousewheel(self) -> None:
        """Install a single Tcl-level mousewheel handler for the canvas.

        On macOS, trackpad two-finger scrolling floods the event loop
        with MouseWheel events (60+ per second).  A Python-level
        ``bind_all`` or per-widget ``bind`` invokes the Python/Tcl bridge
        for every single one, making buttons feel laggy.

        Instead, we install ONE handler in pure Tcl that runs entirely
        inside the Tcl interpreter.  It checks if the cursor is over a
        Text widget (which scrolls itself) or a Button (to avoid
        scroll-during-click), and otherwise scrolls the canvas.  Zero
        Python callbacks fire for mousewheel events.
        """
        canvas_path = str(self._canvas)
        self.root.tk.eval(f'''
            bind all <MouseWheel> {{
                set w [winfo containing %X %Y]
                if {{$w eq ""}} return
                set cls [winfo class $w]
                if {{$cls eq "Text" || $cls eq "Button"}} return
                {canvas_path} yview scroll [expr {{-(%D)}}] units
            }}
        ''')

    # ------------------------------------------------------------------
    # Deferred library loading + loading overlay
    # ------------------------------------------------------------------

    def _preload_libs(self) -> None:
        """Pre-import heavy libraries in a background thread.

        Runs immediately after the GUI appears.  By the time the user
        reads the UI and clicks a button, the imports are usually already
        cached and subsequent ``import`` statements are instant.
        """
        try:
            import pygame                   # noqa: F811 — lazy preload
            import transcribeone            # noqa: F811 — pulls in assemblyai
            if HAS_SHOW_NOTES:
                import anthropic            # noqa: F811
                import show_notes_processor  # noqa: F811
        except Exception:
            pass
        # Signal the main thread that imports are ready.
        self.root.after(0, self._on_libs_ready)

    def _on_libs_ready(self) -> None:
        """Called on the main thread once background pre-import finishes."""
        self._libs_ready = True
        # If the user clicked an action while the overlay was up,
        # dismiss the overlay and run the queued action now.
        if self._overlay is not None:
            self._dismiss_overlay()
        if self._pending_action is not None:
            action = self._pending_action
            self._pending_action = None
            action()

    def _require_libs(self, action) -> bool:
        """Gate an action on heavy libs being loaded.

        If libs are ready, returns True and the caller should proceed.
        If not, shows a loading overlay and queues *action* to run when
        the imports finish.  Returns False (caller should return early).
        """
        if self._libs_ready:
            return True
        self._pending_action = action
        self._show_overlay()
        return False

    def _show_overlay(self) -> None:
        """Display a semi-transparent loading overlay over the whole window."""
        if self._overlay is not None:
            return  # already showing
        ov = tk.Frame(self.root, bg="#f5f5f7")
        ov.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Center the message + spinner
        inner = tk.Frame(ov, bg="#f5f5f7")
        inner.place(relx=0.5, rely=0.4, anchor="center")

        tk.Label(
            inner, text="Loading libraries\u2026",
            font=("SF Pro Display", 16, "bold"),
            fg=CLR_TEXT, bg="#f5f5f7",
        ).pack()
        tk.Label(
            inner,
            text="This only happens once after launch.",
            font=("SF Pro Text", 12),
            fg=CLR_TEXT_SEC, bg="#f5f5f7",
        ).pack(pady=(6, 12))
        spinner = ttk.Progressbar(inner, mode="indeterminate", length=220)
        spinner.pack()
        spinner.start(12)

        self._overlay = ov
        ov.lift()   # ensure it's on top of everything

    def _dismiss_overlay(self) -> None:
        """Remove the loading overlay."""
        if self._overlay is not None:
            self._overlay.destroy()
            self._overlay = None

    # ------------------------------------------------------------------
    # File handling
    # ------------------------------------------------------------------

    def _setup_mac_open_document(self) -> None:
        """Handle files dragged onto the app icon in Finder/Dock."""
        try:
            self.root.createcommand("::tk::mac::OpenDocument", self._mac_open_document)
        except Exception:
            pass

    def _mac_open_document(self, *args) -> None:
        """Called by macOS when files are opened via the app."""
        all_formats = SUPPORTED_FORMATS
        if HAS_FFMPEG:
            all_formats = all_formats + VIDEO_FORMATS
        for path in args:
            if path.lower().endswith(all_formats):
                self._set_audio_path(path)
                break

    def _set_audio_path(self, path: str) -> None:
        """Set the audio file path and update the UI."""
        self._stop_playback()
        self._audio_path_var.set(path)
        self._loaded_audio_path = None

    def _is_video_file(self, path: str) -> bool:
        """Check whether the given file is a video that needs conversion."""
        return path.lower().endswith(VIDEO_FORMATS)

    # ------------------------------------------------------------------
    # Audio Player
    # ------------------------------------------------------------------

    def _ensure_mixer(self) -> bool:
        """Lazily import pygame and initialise the mixer on first use.

        Returns True if the mixer is (now) ready.  Stores the imported
        module as ``self._pygame`` so subsequent calls avoid re-import.
        """
        if not HAS_AUDIO:
            return False
        try:
            pg = getattr(self, "_pygame", None)
            if pg is None:
                import pygame as pg
                self._pygame = pg
            if not pg.mixer.get_init():
                pg.mixer.init()
            return True
        except Exception:
            return False

    def _load_audio(self, path: str) -> bool:
        """Load an audio file into pygame mixer. Returns True on success."""
        if not self._ensure_mixer():
            return False
        try:
            self._pygame.mixer.music.load(path)
            # Get duration using Sound object (works for wav/ogg; mp3 may be approximate)
            try:
                snd = self._pygame.mixer.Sound(path)
                self._duration = snd.get_length()
                del snd
            except Exception:
                self._duration = 0.0
            self._loaded_audio_path = path
            self._seek_bar.configure(to=max(self._duration, 1.0))
            self._position_var.set(0.0)
            self._update_time_label(0.0)
            return True
        except Exception as exc:
            messagebox.showerror("Playback Error", f"Cannot load audio file:\n{exc}")
            return False

    def _toggle_playback(self) -> None:
        """Play or pause the audio."""
        if not HAS_AUDIO:
            return

        audio_file = self._audio_path_var.get().strip()
        if not audio_file:
            messagebox.showinfo("No File", "Please select an audio file first.")
            return

        if self._paused:
            self._pygame.mixer.music.unpause()
            self._paused = False
            self._playing = True
            self._play_btn.configure(text="\u23F8 Pause")
            self._start_position_updates()
            return

        if self._playing:
            self._pygame.mixer.music.pause()
            self._paused = True
            self._playing = False
            self._play_btn.configure(text="\u25B6 Play")
            self._stop_position_updates()
            return

        # Not playing — load and start
        if self._loaded_audio_path != audio_file:
            if not self._load_audio(audio_file):
                return

        speed = float(self._speed_var.get().rstrip("x"))

        try:
            self._pygame.mixer.music.play()
            # pygame doesn't support native speed change; we reinit mixer at adjusted frequency
            if speed != 1.0:
                self._apply_speed(speed, audio_file)
        except Exception as exc:
            messagebox.showerror("Playback Error", str(exc))
            return

        self._playing = True
        self._paused = False
        self._play_btn.configure(text="\u23F8 Pause")
        self._start_position_updates()

    def _stop_playback(self) -> None:
        """Stop audio playback."""
        if not HAS_AUDIO:
            return
        try:
            self._pygame.mixer.music.stop()
        except Exception:
            pass
        self._playing = False
        self._paused = False
        self._play_btn.configure(text="\u25B6 Play")
        self._position_var.set(0.0)
        self._update_time_label(0.0)
        self._stop_position_updates()

    def _apply_speed(self, speed: float, audio_file: str) -> None:
        """Reinitialize mixer at an adjusted sample rate to simulate speed change."""
        try:
            self._pygame.mixer.music.stop()
            # Default CD-quality sample rate
            base_freq = 44100
            new_freq = int(base_freq * speed)
            self._pygame.mixer.quit()
            self._pygame.mixer.init(frequency=new_freq)
            self._pygame.mixer.music.load(audio_file)
            self._pygame.mixer.music.play()
            self._loaded_audio_path = audio_file
        except Exception:
            # Fall back to normal speed
            self._pygame.mixer.quit()
            self._pygame.mixer.init()
            self._pygame.mixer.music.load(audio_file)
            self._pygame.mixer.music.play()
            self._loaded_audio_path = audio_file

    def _on_speed_change(self, event=None) -> None:
        """Handle speed combobox change."""
        if not self._playing and not self._paused:
            return
        speed = float(self._speed_var.get().rstrip("x"))
        audio_file = self._audio_path_var.get().strip()
        if audio_file and self._playing:
            # Get current position before restarting
            pos = self._position_var.get()
            self._apply_speed(speed, audio_file)
            try:
                self._pygame.mixer.music.set_pos(pos)
            except Exception:
                pass
            self._playing = True
            self._paused = False
            self._play_btn.configure(text="\u23F8 Pause")

    def _on_seek(self, value) -> None:
        """Handle seek bar drag."""
        if not HAS_AUDIO or not self._playing:
            return
        pos = float(value)
        try:
            self._pygame.mixer.music.play(start=pos)
        except Exception:
            try:
                self._pygame.mixer.music.set_pos(pos)
            except Exception:
                pass
        self._update_time_label(pos)

    def _start_position_updates(self) -> None:
        """Start periodic position updates for the seek bar."""
        self._stop_position_updates()
        self._update_position()

    def _stop_position_updates(self) -> None:
        """Stop periodic position updates."""
        if self._position_update_id is not None:
            self.root.after_cancel(self._position_update_id)
            self._position_update_id = None

    def _update_position(self) -> None:
        """Update seek bar and time label from current playback position."""
        if not self._playing:
            return

        if not self._pygame.mixer.music.get_busy():
            # Playback ended naturally
            self._playing = False
            self._paused = False
            self._play_btn.configure(text="\u25B6 Play")
            self._position_var.set(0.0)
            self._update_time_label(0.0)
            return

        # get_pos() returns milliseconds since play() was called
        pos_ms = self._pygame.mixer.music.get_pos()
        if pos_ms >= 0:
            pos_sec = pos_ms / 1000.0
            self._position_var.set(pos_sec)
            self._update_time_label(pos_sec)

        self._position_update_id = self.root.after(250, self._update_position)

    def _update_time_label(self, pos: float) -> None:
        """Update the time display label."""
        def fmt(seconds: float) -> str:
            m, s = divmod(max(0, int(seconds)), 60)
            return f"{m}:{s:02d}"

        dur = self._duration if self._duration > 0 else 0
        self._time_label.configure(text=f"{fmt(pos)} / {fmt(dur)}")

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def _load_preferences(self) -> None:
        """Load saved preferences on startup.

        Environment variables and local config are read immediately.
        Keychain look-ups are dispatched to a background thread so
        they cannot block the UI (macOS Keychain access can take tens
        of seconds, especially inside an unsigned .app bundle).
        """
        # Check environment variables first (instant)
        env_key = os.getenv("ASSEMBLYAI_API_KEY", "").strip()
        if env_key:
            self._api_key_var.set(env_key)

        env_anthropic = ""
        if HAS_SHOW_NOTES:
            env_anthropic = os.getenv("ANTHROPIC_API_KEY", "").strip()
            if env_anthropic:
                self._anthropic_key_var.set(env_anthropic)

        # Local config file (fast)
        config = load_config()
        if config.get("remember_key"):
            self._remember_key_var.set(True)
        if HAS_SHOW_NOTES and config.get("remember_anthropic_key"):
            self._remember_anthropic_key_var.set(True)

        # Restore output directory
        outdir = config.get("output_dir", "")
        if outdir and os.path.isdir(outdir):
            self._output_dir_var.set(outdir)

        # Keychain look-ups in a background thread (can be slow)
        need_aai = config.get("remember_key") and not env_key
        need_anthropic = (HAS_SHOW_NOTES
                          and config.get("remember_anthropic_key")
                          and not env_anthropic)
        if need_aai or need_anthropic:
            self._status_var.set("Loading saved API keys\u2026")
            threading.Thread(
                target=self._load_keychain_keys,
                args=(need_aai, need_anthropic),
                daemon=True,
            ).start()

    def _load_keychain_keys(self, need_aai: bool, need_anthropic: bool) -> None:
        """Load API keys from macOS Keychain (runs in background thread)."""
        if need_aai:
            key = load_from_keychain()
            if key:
                self.root.after(0, self._api_key_var.set, key)
        if need_anthropic:
            akey = load_from_keychain(account=KEYCHAIN_ANTHROPIC)
            if akey:
                self.root.after(0, self._anthropic_key_var.set, akey)
        self.root.after(0, self._status_var.set, "Ready")

    def _save_preferences(self, blocking: bool = False) -> None:
        """Persist preferences.

        Config file is written immediately (fast).  Keychain writes use
        subprocess and can block for seconds on macOS, so by default
        they run in a background thread.  Pass ``blocking=True`` (used
        at app close) to wait for them.
        """
        remember = self._remember_key_var.get()
        remember_anthropic = self._remember_anthropic_key_var.get()
        outdir = self._output_dir_var.get().strip()
        save_config({
            "remember_key": remember,
            "remember_anthropic_key": remember_anthropic,
            "output_dir": outdir,
        })

        keys_to_save: list[tuple[str, str]] = []
        if remember:
            api_key = self._api_key_var.get().strip()
            if api_key:
                keys_to_save.append((api_key, KEYCHAIN_ACCOUNT))
        if remember_anthropic:
            anthropic_key = self._anthropic_key_var.get().strip()
            if anthropic_key:
                keys_to_save.append((anthropic_key, KEYCHAIN_ANTHROPIC))

        if keys_to_save:
            if blocking:
                self._write_keychain_keys(keys_to_save)
            else:
                threading.Thread(
                    target=self._write_keychain_keys,
                    args=(keys_to_save,),
                    daemon=True,
                ).start()

    @staticmethod
    def _write_keychain_keys(keys: list[tuple[str, str]]) -> None:
        """Write API keys to macOS Keychain (may block)."""
        for value, account in keys:
            save_to_keychain(value, account=account)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _toggle_api_key_visibility(self) -> None:
        """Toggle between masked and visible API key."""
        self._show_key = not self._show_key
        self._api_key_entry.configure(show="" if self._show_key else "*")
        self._toggle_btn.configure(text="Hide" if self._show_key else "Show")

    # ------------------------------------------------------------------
    # API key verification
    # ------------------------------------------------------------------

    def _verify_assemblyai_key(self) -> None:
        """Verify the AssemblyAI API key with a lightweight API call."""
        if self._verifying_assemblyai:
            return
        api_key = self._api_key_var.get().strip()
        if not api_key:
            self._aai_verify_label.configure(text="Please enter a key first", foreground=CLR_ERROR)
            return
        self._verifying_assemblyai = True
        self._verify_aai_btn.configure(state="disabled")
        self._aai_verify_label.configure(text="Verifying\u2026", foreground=CLR_TEXT_SEC)
        self._status_var.set("Verifying AssemblyAI key\u2026")
        self._progress.start(10)
        threading.Thread(
            target=self._verify_assemblyai_worker, args=(api_key,), daemon=True,
        ).start()

    def _verify_assemblyai_worker(self, api_key: str) -> None:
        """Background: GET transcript list endpoint to validate key."""
        import urllib.request
        import urllib.error
        try:
            req = urllib.request.Request(
                "https://api.assemblyai.com/v2/transcript?limit=1",
                headers={"Authorization": api_key},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    self.root.after(0, self._on_verify_assemblyai_result, True, "")
                else:
                    self.root.after(0, self._on_verify_assemblyai_result, False, f"HTTP {resp.status}")
        except urllib.error.HTTPError as exc:
            msg = "Invalid API key" if exc.code == 401 else f"HTTP {exc.code}"
            self.root.after(0, self._on_verify_assemblyai_result, False, msg)
        except Exception as exc:
            self.root.after(0, self._on_verify_assemblyai_result, False, str(exc))

    def _on_verify_assemblyai_result(self, success: bool, error: str) -> None:
        """Handle AssemblyAI verification result on main thread."""
        self._progress.stop()
        self._verifying_assemblyai = False
        self._verify_aai_btn.configure(state="normal")
        if success:
            self._aai_verify_label.configure(text="\u2713 Valid API key", foreground=CLR_SUCCESS)
            self._status_var.set("AssemblyAI key verified")
        else:
            self._aai_verify_label.configure(text=f"\u2717 {error}", foreground=CLR_ERROR)
            self._status_var.set("AssemblyAI key verification failed")

    def _verify_anthropic_key(self) -> None:
        """Verify the Anthropic API key with a lightweight API call."""
        if not self._require_libs(self._verify_anthropic_key):
            return
        if self._verifying_anthropic:
            return
        api_key = self._anthropic_key_var.get().strip()
        if not api_key:
            self._anthropic_verify_label.configure(text="Please enter a key first", foreground=CLR_ERROR)
            return
        self._verifying_anthropic = True
        self._verify_anthropic_btn.configure(state="disabled")
        self._anthropic_verify_label.configure(text="Verifying\u2026", foreground=CLR_TEXT_SEC)
        self._status_var.set("Verifying Anthropic key\u2026")
        self._progress.start(10)
        threading.Thread(
            target=self._verify_anthropic_worker, args=(api_key,), daemon=True,
        ).start()

    def _verify_anthropic_worker(self, api_key: str) -> None:
        """Background: call Anthropic models.list() to validate key."""
        import anthropic  # deferred import — heavy lib loaded in bg thread

        try:
            client = anthropic.Anthropic(api_key=api_key)
            client.models.list()
            self.root.after(0, self._on_verify_anthropic_result, True, "")
        except anthropic.AuthenticationError:
            self.root.after(0, self._on_verify_anthropic_result, False, "Invalid API key")
        except Exception as exc:
            self.root.after(0, self._on_verify_anthropic_result, False, str(exc))

    def _on_verify_anthropic_result(self, success: bool, error: str) -> None:
        """Handle Anthropic verification result on main thread."""
        self._progress.stop()
        self._verifying_anthropic = False
        self._verify_anthropic_btn.configure(state="normal")
        if success:
            self._anthropic_verify_label.configure(text="\u2713 Valid API key", foreground=CLR_SUCCESS)
            self._status_var.set("Anthropic key verified")
        else:
            self._anthropic_verify_label.configure(text=f"\u2717 {error}", foreground=CLR_ERROR)
            self._status_var.set("Anthropic key verification failed")

    def _on_assemblyai_key_changed(self, *args) -> None:
        """Clear verification feedback when the AssemblyAI key is edited."""
        if hasattr(self, "_aai_verify_label"):
            self._aai_verify_label.configure(text="")

    def _on_anthropic_key_changed(self, *args) -> None:
        """Clear verification feedback when the Anthropic key is edited."""
        if hasattr(self, "_anthropic_verify_label"):
            self._anthropic_verify_label.configure(text="")

    def _browse_file(self) -> None:
        """Open a native file dialog for audio selection."""
        filetypes = list(AUDIO_FILETYPES)
        if HAS_FFMPEG:
            video_exts = " ".join(f"*{ext}" for ext in VIDEO_FORMATS)
            audio_exts = filetypes[0][1]
            filetypes = [
                ("Media files", f"{audio_exts} {video_exts}"),
                ("Audio files", audio_exts),
                ("Video files", video_exts),
                ("All files", "*.*"),
            ]

        path = filedialog.askopenfilename(
            title="Select Media File",
            filetypes=filetypes,
        )
        if path:
            self._set_audio_path(path)

    def _browse_output_dir(self) -> None:
        """Open a native directory dialog for output location."""
        path = filedialog.askdirectory(title="Select Output Directory")
        if path:
            self._output_dir_var.set(path)

    def _cleanup_tmp_audio(self) -> None:
        """Remove any temporary audio file from a previous video conversion."""
        if self._tmp_audio_file and os.path.exists(self._tmp_audio_file):
            try:
                os.remove(self._tmp_audio_file)
            except OSError:
                pass
            self._tmp_audio_file = ""

    @staticmethod
    def _validate_audio_file(audio_file: str) -> None:
        """Validate audio file without importing transcribeone.

        Mirrors transcribeone.validate_audio_file() to avoid loading the
        heavy assemblyai library on the main thread.
        """
        if not os.path.exists(audio_file):
            raise ValueError(f"File not found: {audio_file}")
        if not os.path.isfile(audio_file):
            raise ValueError(f"Not a file: {audio_file}")
        if not os.access(audio_file, os.R_OK):
            raise ValueError(f"Permission denied: {audio_file}")
        if os.path.getsize(audio_file) == 0:
            raise ValueError(f"File is empty: {audio_file}")
        if not audio_file.lower().endswith(SUPPORTED_FORMATS):
            raise ValueError(
                f"Unsupported audio format: {audio_file}\n"
                f"Supported formats: {', '.join(SUPPORTED_FORMATS)}"
            )

    def _start_transcription(self) -> None:
        """Validate inputs and launch the background transcription."""
        if not self._require_libs(self._start_transcription):
            return
        try:
            if self._transcribing:
                return

            api_key = self._api_key_var.get().strip()
            audio_file = self._audio_path_var.get().strip()

            if not api_key:
                messagebox.showerror("Missing API Key", "Please enter your AssemblyAI API key.")
                return

            if not audio_file:
                messagebox.showerror("No File Selected", "Please select an audio file to transcribe.")
                return

            # If it's a video file, we'll convert in the worker thread
            is_video = self._is_video_file(audio_file)

            if not is_video:
                try:
                    self._validate_audio_file(audio_file)
                except ValueError as exc:
                    messagebox.showerror("Invalid File", str(exc))
                    return
            else:
                if not os.path.isfile(audio_file):
                    messagebox.showerror("File Not Found", f"Cannot find: {audio_file}")
                    return
            self._save_preferences()

            # Parse speaker names
            raw_names = self._speaker_names_var.get().strip()
            speaker_names = [n.strip() for n in raw_names.split(",") if n.strip()] if raw_names else []

            # Lock UI
            self._transcribing = True
            self._set_ui_busy(True)

            if is_video:
                self._status_var.set("Converting video to audio\u2026")
            else:
                self._status_var.set("Uploading and transcribing\u2026")
            self._progress.start(10)

            thread = threading.Thread(
                target=self._transcription_worker,
                args=(audio_file, api_key, speaker_names, is_video),
                daemon=True,
            )
            thread.start()

        except Exception as exc:
            messagebox.showerror("Error", f"Failed to start transcription:\n{exc}")
            self._transcribing = False
            self._set_ui_busy(False)

    def _transcription_worker(self, audio_file: str, api_key: str, speaker_names: list[str], is_video: bool = False) -> None:
        """Run transcription in a background thread. Must NOT touch tkinter."""
        import transcribeone  # deferred — pulls in assemblyai (heavy)

        try:
            self._cleanup_tmp_audio()

            # Convert video to audio if needed
            actual_audio = audio_file
            if is_video:
                actual_audio = convert_video_to_audio(audio_file)
                self._tmp_audio_file = actual_audio
                self.root.after(0, self._status_var.set, "Uploading and transcribing\u2026")

            transcribeone.set_api_key(api_key)
            transcript_id, results = transcribeone.run_transcription(actual_audio)

            speakers_identified = False
            if results and speaker_names:
                self.root.after(0, self._status_var.set, "Identifying speakers\u2026")
                identified = transcribeone.identify_speakers(
                    transcript_id, api_key,
                    speaker_type="name",
                    known_values=speaker_names,
                )
                if identified:
                    results = identified
                    speakers_identified = True

            # Use original file path for display/save purposes
            self.root.after(0, self._on_transcription_complete, audio_file, results, speakers_identified)
        except Exception as exc:
            self.root.after(0, self._on_transcription_error, str(exc))

    @staticmethod
    def _format_speaker(label: str, identified: bool) -> str:
        """Format a speaker label for display.

        Generic diarization labels (single letters like A, B) get
        prefixed with 'SPEAKER '.  Identified names are used as-is.
        """
        if identified or len(label) > 1:
            return label
        return f"SPEAKER {label}"

    def _on_transcription_complete(self, audio_file: str, results: list[tuple[str, str]], speakers_identified: bool = False) -> None:
        """Display results and auto-save (called on main thread)."""
        self._progress.stop()
        self._set_ui_busy(False)
        self._transcribing = False
        self._current_audio_file = audio_file
        self._raw_results = results

        # Show rename panel when we have generic labels
        if results and not speakers_identified:
            self._build_rename_fields(results)
        else:
            self._rename_outer.pack_forget()

        # Render transcript and save
        self._render_transcript(speakers_identified)
        self._auto_save()

        if not speakers_identified and self._speaker_names_var.get().strip():
            self._status_var.set("Done (speaker identification unavailable \u2014 using generic labels)")
        else:
            self._status_var.set("Done")

        # Content changed — refresh scroll region
        self._update_scroll_region()

    def _build_rename_fields(self, results: list[tuple[str, str]]) -> None:
        """Show editable name fields for each unique speaker (up to 6)."""
        # Clear previous
        for widget in self._rename_inner.winfo_children():
            widget.destroy()
        self._speaker_name_vars.clear()
        self._apply_names_btn.pack_forget()

        # Discover unique speakers in order of appearance
        seen = set()
        speakers = []
        for speaker, _ in results:
            if speaker not in seen:
                seen.add(speaker)
                speakers.append(speaker)
                if len(speakers) >= 6:
                    break

        for speaker in speakers:
            row = ttk.Frame(self._rename_inner, style="Card.TFrame")
            row.pack(fill="x", pady=2)

            ttk.Label(row, text=f"SPEAKER {speaker}:", width=14, anchor="w", style="Card.TLabel").pack(side="left")
            ttk.Label(row, text="\u2192", style="Card.TLabel").pack(side="left", padx=6)

            var = tk.StringVar()
            self._speaker_name_vars[speaker] = var

            entry = ttk.Entry(row, textvariable=var, width=28)
            entry.pack(side="left", fill="x", expand=True)

        self._apply_names_btn.pack(anchor="e", pady=(6, 0))

        # Show the rename frame above the transcript
        self._rename_outer.pack(fill="x", padx=14, pady=5, before=self._result_frame.master.master)

        # Content changed — refresh scroll region
        self._update_scroll_region()

    def _get_speaker_display(self, label: str, identified: bool) -> str:
        """Get the display name for a speaker, checking rename fields first."""
        var = self._speaker_name_vars.get(label)
        if var:
            name = var.get().strip()
            if name:
                return name
        return self._format_speaker(label, identified)

    def _render_transcript(self, speakers_identified: bool = False) -> None:
        """Render the transcript text using current speaker names.

        A blank line is inserted between consecutive lines from different
        speakers to make the transcript easier to read.
        """
        if not self._raw_results:
            text = "No speech detected."
        else:
            parts: list[str] = []
            prev_speaker: str | None = None
            for speaker, utt in self._raw_results:
                if prev_speaker is not None and speaker != prev_speaker:
                    parts.append("")          # blank separator line
                parts.append(f"{self._get_speaker_display(speaker, speakers_identified)}: {utt}")
                prev_speaker = speaker
            text = "\n".join(parts)

        self._result_text.configure(state="normal")
        self._result_text.delete("1.0", "end")
        self._result_text.insert("1.0", text)
        self._result_text.configure(state="disabled")

        self._copy_btn.configure(state="normal")
        self._save_btn.configure(state="normal")

    def _auto_save(self) -> None:
        """Save the current transcript text to the auto-save path.

        Uses the user-selected output directory if set, otherwise saves
        next to the source audio file.
        """
        if not self._current_audio_file:
            return
        text = self._result_text.get("1.0", "end-1c")
        basename = os.path.splitext(os.path.basename(self._current_audio_file))[0]
        filename = f"{basename}-transcript.txt"

        outdir = self._output_dir_var.get().strip()
        if outdir:
            output_path = os.path.join(outdir, filename)
        else:
            output_path = os.path.join(os.path.dirname(self._current_audio_file), filename)

        try:
            with open(output_path, "w") as f:
                f.write(text + "\n")
            self._output_path_label.configure(text=f"Saved: {output_path}")
        except OSError as exc:
            self._output_path_label.configure(text="")
            self._status_var.set(f"Done (save failed: {exc})")

    def _apply_speaker_names(self) -> None:
        """Re-render and re-save transcript with updated speaker names."""
        self._render_transcript(speakers_identified=False)
        self._auto_save()
        self._status_var.set("Names applied and saved")

    def _on_transcription_error(self, error_message: str) -> None:
        """Show error to the user (called on main thread)."""
        self._progress.stop()
        self._set_ui_busy(False)
        self._transcribing = False
        self._status_var.set("Error")
        messagebox.showerror("Transcription Error", error_message)

    def _set_ui_busy(self, busy: bool) -> None:
        """Enable or disable interactive controls during transcription."""
        state = "disabled" if busy else "normal"
        self._transcribe_btn.configure(state=state)
        self._api_key_entry.configure(state=state)
        self._toggle_btn.configure(state=state)
        self._verify_aai_btn.configure(state=state)
        if HAS_SHOW_NOTES:
            self._anthropic_key_entry.configure(state=state)
            self._anthropic_toggle_btn.configure(state=state)
            self._verify_anthropic_btn.configure(state=state)

    def _copy_to_clipboard(self) -> None:
        """Copy the transcript to the system clipboard."""
        text = self._result_text.get("1.0", "end-1c")
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self._status_var.set("Copied to clipboard")

    def _save_to_file(self) -> None:
        """Save transcript via a file dialog."""
        text = self._result_text.get("1.0", "end-1c")
        if not text:
            return

        # Default filename based on audio file
        audio = self._audio_path_var.get()
        default_name = ""
        if audio:
            default_name = os.path.splitext(os.path.basename(audio))[0] + "-transcript.txt"

        path = filedialog.asksaveasfilename(
            title="Save Transcript",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=default_name,
        )
        if path:
            with open(path, "w") as f:
                f.write(text + "\n")
            self._status_var.set(f"Saved to {os.path.basename(path)}")

    def _on_close(self) -> None:
        """Handle window close."""
        self._stop_playback()
        self._save_preferences(blocking=True)
        self._cleanup_tmp_audio()
        pg = getattr(self, "_pygame", None)
        if pg is not None and pg.mixer.get_init():
            try:
                pg.mixer.quit()
            except Exception:
                pass
        self.root.destroy()

    # ------------------------------------------------------------------
    # Show Notes Generator
    # ------------------------------------------------------------------

    def _toggle_anthropic_key_visibility(self) -> None:
        """Toggle between masked and visible Anthropic API key."""
        self._show_anthropic_key = not self._show_anthropic_key
        self._anthropic_key_entry.configure(
            show="" if self._show_anthropic_key else "*"
        )
        self._anthropic_toggle_btn.configure(
            text="Hide" if self._show_anthropic_key else "Show"
        )

    def _start_show_notes(self) -> None:
        """Validate inputs and launch background show-notes generation."""
        if not self._require_libs(self._start_show_notes):
            return
        if not HAS_SHOW_NOTES:
            messagebox.showerror(
                "Unavailable",
                "Show notes processor is not available.\n"
                "Install: pip install anthropic python-docx",
            )
            return

        if self._generating_notes:
            return

        api_key = self._anthropic_key_var.get().strip()
        if not api_key:
            messagebox.showerror(
                "Missing API Key",
                "Please enter your Anthropic API key.",
            )
            return

        # Get transcript text
        transcript_text = self._result_text.get("1.0", "end-1c").strip()
        if not transcript_text or transcript_text == "No speech detected.":
            messagebox.showerror(
                "No Transcript",
                "Please transcribe an audio file first.",
            )
            return

        # Determine output directory
        outdir = self._output_dir_var.get().strip()
        if not outdir and self._current_audio_file:
            outdir = os.path.dirname(self._current_audio_file)
        if not outdir:
            outdir = os.path.expanduser("~/Desktop")

        # Save Anthropic key preferences
        self._save_preferences()

        # Lock UI
        self._generating_notes = True
        self._generate_btn.configure(state="disabled")
        self._status_var.set("Generating show notes with Claude\u2026")
        self._progress.start(10)
        self._notes_output_label.configure(text="")

        thread = threading.Thread(
            target=self._show_notes_worker,
            args=(transcript_text, api_key, outdir),
            daemon=True,
        )
        thread.start()

    def _show_notes_worker(self, transcript_text: str, api_key: str,
                           output_dir: str) -> None:
        """Run show-notes generation in a background thread."""
        import show_notes_processor  # deferred import — heavy lib loaded in bg thread

        try:
            result = show_notes_processor.process_transcript(
                transcript_text, api_key, output_dir,
            )
            self.root.after(0, self._on_show_notes_complete, result)
        except Exception as exc:
            self.root.after(0, self._on_show_notes_error, str(exc))

    def _on_show_notes_complete(self, result: dict) -> None:
        """Handle successful show-notes generation (main thread)."""
        self._progress.stop()
        self._generating_notes = False
        self._generate_btn.configure(state="normal")
        self._status_var.set("Show notes generated")

        docx_path = result.get("docx_path", "")
        md_path = result.get("md_path", "")
        title = result.get("title", "")
        guest = result.get("guest", "")

        info = f"Saved: {os.path.basename(docx_path)}  |  {os.path.basename(md_path)}"
        self._notes_output_label.configure(text=info)

        detail = f"Show notes generated for: {title}"
        if guest and guest.lower() != "none":
            detail += f"\nGuest: {guest}"
        detail += f"\n\n.docx: {docx_path}\n.md:   {md_path}"
        messagebox.showinfo("Show Notes Ready", detail)

    def _on_show_notes_error(self, error_message: str) -> None:
        """Handle show-notes generation error (main thread)."""
        self._progress.stop()
        self._generating_notes = False
        self._generate_btn.configure(state="normal")
        self._status_var.set("Show notes error")
        messagebox.showerror("Show Notes Error", error_message)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Launch the GUI."""
    root = tk.Tk()

    app = TranscribeOneApp(root)
    root.protocol("WM_DELETE_WINDOW", app._on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
