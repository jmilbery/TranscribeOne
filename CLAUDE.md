# CLAUDE.md

## Project Overview

TranscribeOne is a macOS desktop application (and CLI tool) for transcribing audio and video files with automatic speaker labels, powered by the AssemblyAI API.

## Tech Stack

- **Language:** Python 3.10+
- **GUI:** tkinter / ttk with tkinterdnd2 (drag-and-drop)
- **Audio Playback:** pygame
- **Transcription API:** AssemblyAI (via `assemblyai` Python SDK + direct HTTP for Speech Understanding)
- **Video Conversion:** ffmpeg (optional, detected at runtime)
- **Packaging:** PyInstaller (macOS .app bundle + .dmg)
- **License:** CC0 1.0 Universal (Public Domain)

## Project Structure

```
transcribeone.py        # Core library and CLI tool
transcribeone_gui.py    # macOS GUI application (tkinter)
test_transcribeone.py   # Test suite (65 tests)
TranscribeOne.spec      # PyInstaller build configuration
build_app.sh            # Build script for .app and .dmg
requirements.txt        # Python dependencies
docs/                   # GitHub Pages site (Jekyll + Cayman theme)
  _config.yml
  index.md
README.md               # Project readme
LICENSE                  # CC0 1.0 license
CLAUDE.md               # This file
```

## Running

### GUI (primary)

```bash
export ASSEMBLYAI_API_KEY="your-key"
python transcribeone_gui.py
```

The API key can also be entered in the GUI and optionally stored in the macOS Keychain.

### CLI

```bash
export ASSEMBLYAI_API_KEY="your-key"
./transcribeone.py <audio_file>
./transcribeone.py <audio_file> > output.txt   # save transcript
```

### Building the Mac App

```bash
bash build_app.sh
# Output: dist/TranscribeOne.app and dist/TranscribeOne-1.0.0.dmg
```

## Dependencies

```bash
pip install -r requirements.txt
```

Packages: `assemblyai>=0.20.0`, `tkinterdnd2>=0.3.0`, `pygame>=2.5.0`, `pyinstaller>=6.0.0`

Optional: `brew install ffmpeg` (enables video-to-audio conversion)

## Architecture

### transcribeone.py (Core)

Function-based architecture (no classes). Exposes reusable functions for both CLI and GUI:

- `set_api_key(key)` — configure the AssemblyAI API key at runtime
- `validate_audio_file(path)` — validate file exists and has supported extension
- `run_transcription(path)` — upload and transcribe, returns `(transcript_id, [(speaker, text), ...])`
- `identify_speakers(transcript_id, api_key, speaker_type, known_values)` — call Speech Understanding API for speaker identification; returns empty list on failure for graceful fallback
- `SUPPORTED_FORMATS` — tuple of supported audio extensions
- `TranscribeError` — custom exception class

CLI-specific: `load_api_key()`, `parse_args()`, `transcribe_audio()`, `main()`

### transcribeone_gui.py (GUI)

Single class `TranscribeOneApp` with card-based UI sections:

- **API Key** — entry with show/hide toggle, keychain storage, env var pre-fill
- **Source Media** — drag-and-drop zone + file browser; accepts audio and video (with ffmpeg)
- **Player** — pygame-based playback with play/pause, stop, speed control (0.5x–2.0x), seek bar
- **Speaker Names** — comma-separated pre-transcription name entry for speaker identification
- **Rename Speakers** — post-transcription fallback fields (up to 6 speakers) when API identification fails
- **Transcript** — read-only text display with copy/save buttons; auto-saves as `<filename>-transcript.txt`

Key patterns:
- Background transcription via `threading.Thread` with `root.after()` for UI updates
- Video files auto-converted to WAV via ffmpeg subprocess before transcription
- macOS focus fix: `root.bind_all("<Button-1>", ...)` forces focus to clicked widget
- `TkinterDnD.Tk()` root when available, falls back to standard `tk.Tk()`

## Code Conventions

- All functions have type hints and docstrings
- GUI uses ttk styles with a consistent color palette (Apple-inspired)
- Section cards created via `_create_section()` helper (icon + title + content frame)
- Speaker labels: single-letter generic labels get `SPEAKER ` prefix; identified names display as-is
- Output format: `SPEAKER A: <text>` (generic) or `Name: <text>` (identified)
- Errors surfaced to user via `messagebox.showerror()`
- API key sources (priority order): env var `ASSEMBLYAI_API_KEY` → macOS Keychain

## Testing

```bash
source .venv/bin/activate
python -m pytest test_transcribeone.py -v
```

65 tests covering: `TestSetApiKey`, `TestValidateAudioFile`, `TestRunTranscription`, `TestIdentifySpeakers`, `TestLoadApiKey`, `TestParseArgs`, `TestTranscribeAudio`, `TestMain`, `TestIntegration`

## Notes

- `.gitignore` excludes `*-transcript.txt` and `*.mp3` files
- The built `.app` is unsigned; users must right-click > Open on first launch
- GitHub Pages site at https://jmilbery.github.io/TranscribeOne
- Speech Understanding API is called via `urllib.request` (not yet in the assemblyai Python SDK)
