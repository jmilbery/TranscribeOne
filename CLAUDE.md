# CLAUDE.md

## Project Overview

TranscribeOne is a macOS desktop application (and CLI tool) for transcribing audio and video files with automatic speaker labels, powered by the AssemblyAI API. Includes integrated show-notes generation via the Claude API for the Private Equity Funcast podcast.

## Tech Stack

- **Language:** Python 3.10+
- **GUI:** tkinter / ttk (browse-only file selection)
- **Audio Playback:** pygame
- **Transcription API:** AssemblyAI (via `assemblyai` Python SDK + direct HTTP for Speech Understanding)
- **Show Notes Generation:** Anthropic Claude API (via `anthropic` Python SDK) + `python-docx`
- **Video Conversion:** ffmpeg (optional, detected at runtime)
- **Packaging:** PyInstaller (macOS .app bundle + .dmg)
- **License:** CC0 1.0 Universal (Public Domain)

## Project Structure

```
transcribeone.py          # Core library and CLI tool
transcribeone_gui.py      # macOS GUI application (tkinter)
show_notes_processor.py   # Claude API integration + .docx generation
test_transcribeone.py     # Test suite (65 tests)
TranscribeOne.spec        # PyInstaller build configuration
build_app.sh              # Build script for .app and .dmg
requirements.txt          # Python dependencies
docs/                     # GitHub Pages site (Jekyll + Cayman theme)
  _config.yml
  index.md
README.md                 # Project readme
LICENSE                   # CC0 1.0 license
CLAUDE.md                 # This file
```

## Running

### GUI (primary)

```bash
export ASSEMBLYAI_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"  # optional, for show notes generation
python transcribeone_gui.py
```

Both API keys can also be entered in the GUI and optionally stored in the macOS Keychain.

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

Packages: `assemblyai>=0.20.0`, `pygame>=2.5.0`, `anthropic>=0.40.0`, `python-docx>=1.0.0`, `pyinstaller>=6.0.0`

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

- **API Keys** — consolidated section with AssemblyAI and Anthropic key entries, each with show/hide toggle, "Remember" checkbox (Keychain), and Verify button
- **Source Media** — file browser; accepts audio and video (with ffmpeg)
- **Player** — pygame-based playback with play/pause, stop, speed control (0.5x–2.0x), seek bar
- **Output Directory** — user-selected output folder for transcripts and show notes
- **Speaker Names** — comma-separated pre-transcription name entry for speaker identification
- **Rename Speakers** — post-transcription fallback fields (up to 6 speakers) when API identification fails
- **Transcript** — read-only text display with copy/save buttons; auto-saves as `<filename>-transcript.txt`
- **Show Notes Generator** — "Generate Show Notes" button; produces .docx and .md
- **Fixed Status Bar** — always-visible bar at window bottom with status text and progress spinner

Key patterns:
- **Deferred imports:** All heavy libraries (pygame, assemblyai, anthropic) use `importlib.util.find_spec()` for availability checks at module level. Actual imports are deferred to background threads or first use, so the GUI launches instantly even in PyInstaller bundles where Gatekeeper scanning causes 10-30s import delays.
- **Background pre-import:** A background thread starts importing heavy libs immediately after the GUI appears. By the time the user interacts, imports are usually cached.
- **Loading overlay:** If the user clicks an action before pre-import finishes, a full-window overlay with spinner appears and auto-dismisses when ready, then the queued action executes.
- **Lazy pygame mixer:** `pygame.mixer.init()` is deferred to first audio playback via `_ensure_mixer()`. The `pygame` module reference is stored as `self._pygame`.
- **Canvas-based scrolling** with a single Tcl-level `bind all <MouseWheel>` handler (avoids Python/Tcl bridge overhead that makes macOS trackpad events laggy). No `<Configure>` binding on the scroll frame — scroll region updated explicitly at known content-change points.
- Background transcription via `threading.Thread` with `root.after()` for UI updates
- Video files auto-converted to WAV via ffmpeg subprocess before transcription
- All buttons use `tk.Button` (not `ttk.Button`) for reliable macOS click handling
- Keychain load/save operations run in background threads to avoid blocking the UI
- `SUPPORTED_FORMATS` is duplicated in the GUI to avoid importing `transcribeone` (and thus `assemblyai`) at module level

### show_notes_processor.py (Claude API Integration)

Handles transcript processing via the Anthropic Claude API and .docx generation:

- `generate_show_notes(transcript_text, api_key, model)` — sends transcript to Claude, returns parsed response
- `parse_response(response_text)` — extracts metadata, show notes, and social snippets from Claude's delimited output
- `save_show_notes_docx(parsed, output_path)` — builds formatted .docx using `python-docx`
- `save_social_snippets_md(parsed, output_path)` — saves social snippets markdown
- `process_transcript(transcript_text, api_key, output_dir)` — full pipeline orchestrator

Adapted from the "podcast-transcribe-and-summarize" Claude skill for the Private Equity Funcast.
Output: `show-notes-[slug].docx` + `social-snippets-[slug].md`

## Code Conventions

- All functions have type hints and docstrings
- GUI uses ttk styles with a consistent color palette (Apple-inspired)
- Section cards created via `_create_section()` helper (icon + title + content frame)
- Speaker labels: single-letter generic labels get `SPEAKER ` prefix; identified names display as-is
- Output format: `SPEAKER A: <text>` (generic) or `Name: <text>` (identified)
- Errors surfaced to user via `messagebox.showerror()`
- API key sources (priority order): env var → macOS Keychain → manual entry
- Keychain functions parameterized by `account` to support multiple keys (AssemblyAI + Anthropic)
- Heavy library imports are always deferred — never import `pygame`, `assemblyai`, `anthropic`, or `show_notes_processor` at module level in the GUI

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
