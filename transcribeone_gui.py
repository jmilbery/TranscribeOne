#!/usr/bin/env python3

"""
TranscribeOne GUI
-----------------
macOS desktop application for transcribing audio files with speaker
identification using AssemblyAI.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

try:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame
    pygame.mixer.init()
    HAS_AUDIO = True
except Exception:
    HAS_AUDIO = False

import transcribeone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME = "TranscribeOne"
CONFIG_DIR = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
KEYCHAIN_SERVICE = "TranscribeOne"
KEYCHAIN_ACCOUNT = "api_key"
WINDOW_WIDTH = 720
WINDOW_HEIGHT = 1000
AUDIO_FILETYPES = [
    ("Audio files", " ".join(f"*{ext}" for ext in transcribeone.SUPPORTED_FORMATS)),
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
CLR_DROP_BG = "#f0f4ff"        # Drop zone background
CLR_DROP_HOVER = "#dce6f9"     # Drop zone drag-over
CLR_DROP_BD = "#b0c4de"        # Drop zone border
CLR_TEXT = "#1d1d1f"           # Primary text
CLR_TEXT_SEC = "#86868b"       # Secondary text
CLR_SUCCESS = "#34c759"        # Success green
CLR_HEADER = "#1d1d1f"        # Section header text
CLR_BTN_BG = "#e8e8ed"        # Button background
CLR_BTN_FG = "#1d1d1f"        # Button foreground
CLR_BTN_ACTIVE = "#d1d1d6"    # Button active/pressed
CLR_BTN_ACC_BG = "#0071e3"    # Accent button bg
CLR_BTN_ACC_FG = "#ffffff"    # Accent button fg
CLR_BTN_ACC_ACTIVE = "#005bb5" # Accent button active


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

def save_to_keychain(api_key: str) -> bool:
    """Store API key in the macOS Keychain. Returns True on success."""
    subprocess.run(
        ["security", "delete-generic-password",
         "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT],
        capture_output=True,
    )
    result = subprocess.run(
        ["security", "add-generic-password",
         "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT,
         "-w", api_key],
        capture_output=True,
    )
    return result.returncode == 0


def load_from_keychain() -> str:
    """Retrieve API key from the macOS Keychain. Returns empty string if not found."""
    result = subprocess.run(
        ["security", "find-generic-password",
         "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
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
        self._last_drop_time = 0.0

        self._setup_styles()
        self._build_ui()
        self._setup_dnd()
        self._setup_mac_open_document()
        self._load_preferences()

        # Note: we previously used bind_all("<Button-1>") to fix macOS
        # focus issues, but it interfered with tk.Button click delivery
        # and caused spurious browse dialogs after drag-and-drop.  Removed.

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
    def _make_button(parent, text: str, command, accent: bool = False,
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
        }
        if accent:
            opts.update(bg=CLR_BTN_ACC_BG, fg=CLR_BTN_ACC_FG,
                        activebackground=CLR_BTN_ACC_ACTIVE,
                        activeforeground=CLR_BTN_ACC_FG,
                        font=("SF Pro Text", 13, "bold"))
        else:
            opts.update(bg=CLR_BTN_BG, fg=CLR_BTN_FG,
                        activebackground=CLR_BTN_ACTIVE,
                        activeforeground=CLR_BTN_FG)
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

        # --- App Title Bar ---
        title_frame = tk.Frame(self.root, bg=CLR_BG)
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

        # --- API Key ---
        key_content = self._create_section(self.root, "\U0001F511", "API Key")

        key_row = ttk.Frame(key_content, style="Card.TFrame")
        key_row.pack(fill="x")

        self._api_key_entry = ttk.Entry(key_row, textvariable=self._api_key_var, show="*", width=48)
        self._api_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._toggle_btn = self._make_button(key_row, text="Show", command=self._toggle_api_key_visibility, width=6)
        self._toggle_btn.pack(side="left", padx=(0, 6))

        ttk.Checkbutton(key_row, text="Remember", variable=self._remember_key_var).pack(side="left")

        # --- Source Media ---
        # Update label based on ffmpeg availability
        media_title = "Source Media" if HAS_FFMPEG else "Audio File"
        file_content = self._create_section(self.root, "\U0001F3B5", media_title)

        # Drop zone
        self._drop_frame = tk.Frame(
            file_content, bg=CLR_DROP_BG, relief="flat", bd=0,
            highlightbackground=CLR_DROP_BD, highlightthickness=2, height=50,
        )
        self._drop_frame.pack(fill="x", pady=(0, 6))
        self._drop_frame.pack_propagate(False)

        drop_text = "Drop audio file here or click to browse" if HAS_DND else "Click to select audio file"
        if HAS_FFMPEG:
            drop_text = "Drop audio or video file here or click to browse" if HAS_DND else "Click to select audio or video file"
        self._drop_label = tk.Label(
            self._drop_frame,
            text=drop_text,
            bg=CLR_DROP_BG, fg=CLR_TEXT_SEC,
            font=("SF Pro Text", 12),
        )
        self._drop_label.pack(expand=True)

        # Make the drop zone clickable (but not when a drop just happened)
        self._drop_frame.bind("<Button-1>", self._on_drop_zone_click)
        self._drop_label.bind("<Button-1>", self._on_drop_zone_click)

        path_row = ttk.Frame(file_content, style="Card.TFrame")
        path_row.pack(fill="x")

        self._path_entry = ttk.Entry(path_row, textvariable=self._audio_path_var, state="readonly", takefocus=False)
        self._path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._make_button(path_row, text="Browse\u2026", command=self._browse_file).pack(side="left")

        fmt_list = ", ".join(ext.lstrip(".") for ext in transcribeone.SUPPORTED_FORMATS)
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
        player_content = self._create_section(self.root, "\U0001F50A", "Player")

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

        # --- Speaker Names ---
        names_content = self._create_section(self.root, "\U0001F465", "Speaker Names (optional)")

        self._speaker_names_var = tk.StringVar()
        names_entry = ttk.Entry(names_content, textvariable=self._speaker_names_var)
        names_entry.pack(fill="x")

        ttk.Label(
            names_content,
            text="Enter expected speaker names separated by commas (e.g. Alice, Bob)",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        # --- Transcribe ---
        ctrl_frame = tk.Frame(self.root, bg=CLR_BG)
        ctrl_frame.pack(fill="x", padx=14, pady=(3, 1))

        self._transcribe_btn = self._make_button(
            ctrl_frame, text="\u25B6  Transcribe",
            command=self._start_transcription, accent=True,
        )
        self._transcribe_btn.pack(side="right")

        # --- Status / Progress ---
        status_frame = ttk.Frame(self.root, style="Status.TFrame")
        status_frame.pack(fill="x", padx=14, pady=(0, 2))

        self._status_label = ttk.Label(status_frame, textvariable=self._status_var, style="Status.TLabel")
        self._status_label.pack(side="left")

        self._progress = ttk.Progressbar(status_frame, mode="indeterminate", length=200)
        self._progress.pack(side="right")

        # --- Speaker Rename (shown after transcription if API identification failed) ---
        self._rename_outer = tk.Frame(self.root, bg=CLR_SECTION_BD, bd=0, highlightthickness=0)
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
        result_outer = tk.Frame(self.root, bg=CLR_SECTION_BD, bd=0, highlightthickness=0)
        result_outer.pack(fill="both", expand=True, padx=14, pady=5)

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

    # ------------------------------------------------------------------
    # Drag-and-drop
    # ------------------------------------------------------------------

    def _setup_dnd(self) -> None:
        """Register drag-and-drop on the drop zone if tkinterdnd2 is available."""
        if not HAS_DND:
            return

        self._drop_frame.drop_target_register(DND_FILES)
        self._drop_frame.dnd_bind("<<DropEnter>>", self._on_drag_enter)
        self._drop_frame.dnd_bind("<<DropLeave>>", self._on_drag_leave)
        self._drop_frame.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drag_enter(self, event) -> None:
        """Visual feedback when dragging over the drop zone."""
        self._drop_frame.configure(bg=CLR_DROP_HOVER, highlightbackground=CLR_ACCENT)
        self._drop_label.configure(bg=CLR_DROP_HOVER, fg=CLR_TEXT)

    def _on_drag_leave(self, event) -> None:
        """Restore drop zone appearance when drag leaves."""
        self._drop_frame.configure(bg=CLR_DROP_BG, highlightbackground=CLR_DROP_BD)
        current = self._audio_path_var.get()
        if current:
            self._drop_label.configure(bg=CLR_DROP_BG, fg=CLR_TEXT)
        else:
            self._drop_label.configure(bg=CLR_DROP_BG, fg=CLR_TEXT_SEC)

    def _on_drop_zone_click(self, event) -> None:
        """Open file browser when the drop zone is clicked (not after a drop)."""
        if time.time() - self._last_drop_time < 0.5:
            return
        self._browse_file()

    def _on_drop(self, event) -> None:
        """Handle file drop onto the drop zone."""
        self._last_drop_time = time.time()
        self._drop_frame.configure(bg=CLR_DROP_BG, highlightbackground=CLR_DROP_BD)
        self._drop_label.configure(bg=CLR_DROP_BG)

        # tkinterdnd2 wraps paths with spaces in {braces}
        raw = event.data.strip()
        if raw.startswith("{") and raw.endswith("}"):
            path = raw[1:-1]
        else:
            # Could be multiple files — take the first one
            path = raw.split()[0] if raw else ""

        if not path:
            return

        # Check for supported formats (audio + video if ffmpeg available)
        all_formats = transcribeone.SUPPORTED_FORMATS
        if HAS_FFMPEG:
            all_formats = all_formats + VIDEO_FORMATS

        if not path.lower().endswith(all_formats):
            messagebox.showwarning(
                "Unsupported File",
                f"Please drop a supported file.\n\n"
                f"Audio: {', '.join(transcribeone.SUPPORTED_FORMATS)}"
                + (f"\nVideo: {', '.join(VIDEO_FORMATS)}" if HAS_FFMPEG else ""),
            )
            return

        self._set_audio_path(path)

    def _setup_mac_open_document(self) -> None:
        """Handle files dragged onto the app icon in Finder/Dock."""
        try:
            self.root.createcommand("::tk::mac::OpenDocument", self._mac_open_document)
        except Exception:
            pass

    def _mac_open_document(self, *args) -> None:
        """Called by macOS when files are opened via the app."""
        all_formats = transcribeone.SUPPORTED_FORMATS
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
        self._drop_label.configure(text=os.path.basename(path), fg=CLR_TEXT)
        self._loaded_audio_path = None

    def _is_video_file(self, path: str) -> bool:
        """Check whether the given file is a video that needs conversion."""
        return path.lower().endswith(VIDEO_FORMATS)

    # ------------------------------------------------------------------
    # Audio Player
    # ------------------------------------------------------------------

    def _load_audio(self, path: str) -> bool:
        """Load an audio file into pygame mixer. Returns True on success."""
        if not HAS_AUDIO:
            return False
        try:
            pygame.mixer.music.load(path)
            # Get duration using Sound object (works for wav/ogg; mp3 may be approximate)
            try:
                snd = pygame.mixer.Sound(path)
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
            pygame.mixer.music.unpause()
            self._paused = False
            self._playing = True
            self._play_btn.configure(text="\u23F8 Pause")
            self._start_position_updates()
            return

        if self._playing:
            pygame.mixer.music.pause()
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
            pygame.mixer.music.play()
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
            pygame.mixer.music.stop()
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
            pygame.mixer.music.stop()
            # Default CD-quality sample rate
            base_freq = 44100
            new_freq = int(base_freq * speed)
            pygame.mixer.quit()
            pygame.mixer.init(frequency=new_freq)
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
            self._loaded_audio_path = audio_file
        except Exception:
            # Fall back to normal speed
            pygame.mixer.quit()
            pygame.mixer.init()
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
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
                pygame.mixer.music.set_pos(pos)
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
            pygame.mixer.music.play(start=pos)
        except Exception:
            try:
                pygame.mixer.music.set_pos(pos)
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

        if not pygame.mixer.music.get_busy():
            # Playback ended naturally
            self._playing = False
            self._paused = False
            self._play_btn.configure(text="\u25B6 Play")
            self._position_var.set(0.0)
            self._update_time_label(0.0)
            return

        # get_pos() returns milliseconds since play() was called
        pos_ms = pygame.mixer.music.get_pos()
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
        """Load saved preferences on startup."""
        # Check environment variable first
        env_key = os.getenv("ASSEMBLYAI_API_KEY", "").strip()
        if env_key:
            self._api_key_var.set(env_key)

        # Then check keychain (won't overwrite if env var was set)
        config = load_config()
        if config.get("remember_key"):
            self._remember_key_var.set(True)
            if not env_key:
                key = load_from_keychain()
                if key:
                    self._api_key_var.set(key)

    def _save_preferences(self) -> None:
        """Persist preferences."""
        remember = self._remember_key_var.get()
        save_config({"remember_key": remember})
        if remember:
            api_key = self._api_key_var.get().strip()
            if api_key:
                save_to_keychain(api_key)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _toggle_api_key_visibility(self) -> None:
        """Toggle between masked and visible API key."""
        self._show_key = not self._show_key
        self._api_key_entry.configure(show="" if self._show_key else "*")
        self._toggle_btn.configure(text="Hide" if self._show_key else "Show")

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

    def _cleanup_tmp_audio(self) -> None:
        """Remove any temporary audio file from a previous video conversion."""
        if self._tmp_audio_file and os.path.exists(self._tmp_audio_file):
            try:
                os.remove(self._tmp_audio_file)
            except OSError:
                pass
            self._tmp_audio_file = ""

    def _start_transcription(self) -> None:
        """Validate inputs and launch the background transcription."""
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
                    transcribeone.validate_audio_file(audio_file)
                except ValueError as exc:
                    messagebox.showerror("Invalid File", str(exc))
                    return
            else:
                if not os.path.isfile(audio_file):
                    messagebox.showerror("File Not Found", f"Cannot find: {audio_file}")
                    return

            transcribeone.set_api_key(api_key)
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
        try:
            self._cleanup_tmp_audio()

            # Convert video to audio if needed
            actual_audio = audio_file
            if is_video:
                actual_audio = convert_video_to_audio(audio_file)
                self._tmp_audio_file = actual_audio
                self.root.after(0, self._status_var.set, "Uploading and transcribing\u2026")

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
        """Save the current transcript text to the auto-save path."""
        if not self._current_audio_file:
            return
        text = self._result_text.get("1.0", "end-1c")
        base = os.path.splitext(self._current_audio_file)[0]
        output_path = f"{base}-transcript.txt"
        try:
            with open(output_path, "w") as f:
                f.write(text + "\n")
            self._output_path_label.configure(text=f"Saved: {os.path.basename(output_path)}")
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
        self._save_preferences()
        self._cleanup_tmp_audio()
        if HAS_AUDIO:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
        self.root.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Launch the GUI."""
    # Use TkinterDnD root if available for native drag-and-drop support
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    app = TranscribeOneApp(root)
    root.protocol("WM_DELETE_WINDOW", app._on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
