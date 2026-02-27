---
layout: default
title: TranscribeOne
---

# TranscribeOne

**A macOS desktop app for transcribing audio and video files with automatic speaker labels.**

TranscribeOne makes it easy to turn any audio or video recording into a clean, speaker-labeled transcript. Drop in a file, click Transcribe, and get results in seconds.

---

## Features

### Transcription with Speaker Labels
Automatically detects multiple speakers and labels each line of the transcript. Works with interviews, meetings, podcasts, and any multi-speaker recording.

### Speaker Identification
Enter expected speaker names before transcription and TranscribeOne will attempt to match them to voices in the recording. When automatic matching isn't possible, use the built-in rename fields to assign names manually.

### Audio & Video Support
Supports a wide range of audio formats including MP3, WAV, M4A, FLAC, OGG, WMA, and WebM. With [ffmpeg](https://ffmpeg.org) installed, video files (MP4, MOV, AVI, MKV, and more) are automatically converted to audio before transcription.

### Built-in Audio Player
Play back your audio directly in the app with play/pause, stop, a seek bar, and adjustable playback speed (0.5x to 2.0x).

### Drag and Drop
Drag audio or video files directly from Finder onto the app window. Also supports dragging files onto the app icon in the Dock.

### Auto-Save
Transcripts are automatically saved alongside the source file as `<filename>-transcript.txt`, and can also be copied to the clipboard or saved to a custom location.

---

## Getting Started

### Prerequisites

- **macOS** (tested on macOS 13+)
- **Python 3.10+**
- An **AssemblyAI API key** ([get one free](https://www.assemblyai.com/dashboard/signup))
- **ffmpeg** (optional, for video file support): `brew install ffmpeg`

### Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- [assemblyai](https://pypi.org/project/assemblyai/) - transcription API client
- [tkinterdnd2](https://pypi.org/project/tkinterdnd2/) - native drag-and-drop support
- [pygame](https://pypi.org/project/pygame/) - audio playback
- [pyinstaller](https://pypi.org/project/pyinstaller/) - app bundling

### Run from Source

```bash
export ASSEMBLYAI_API_KEY="your-key-here"
python transcribeone_gui.py
```

### Build the macOS App

```bash
bash build_app.sh
```

This creates:
- `dist/TranscribeOne.app` - the standalone application
- `dist/TranscribeOne-1.0.0.dmg` - a distributable disk image

> **Note:** The app is unsigned. On first launch, right-click the app and select **Open**, or go to **System Settings > Privacy & Security** to allow it.

---

## Command-Line Usage

TranscribeOne also works as a CLI tool:

```bash
export ASSEMBLYAI_API_KEY="your-key-here"
./transcribeone.py recording.mp3
```

Output is printed to stdout with one line per utterance:

```
Speaker A: Welcome to the meeting.
Speaker B: Thanks for having me.
Speaker A: Let's get started with the agenda.
```

Pipe to a file to save:

```bash
./transcribeone.py recording.mp3 > transcript.txt
```

---

## How It Works

TranscribeOne uses the [AssemblyAI](https://www.assemblyai.com) speech-to-text API for transcription and speaker diarization. Here's the flow:

1. **Upload** - Your audio file is uploaded to AssemblyAI's secure servers
2. **Transcribe** - AssemblyAI's AI models convert speech to text with speaker diarization enabled
3. **Identify** - If speaker names are provided, AssemblyAI's Speech Understanding API attempts to match names to speakers based on conversational context
4. **Display** - The labeled transcript appears in the app and is auto-saved to disk

### About AssemblyAI

[AssemblyAI](https://www.assemblyai.com) provides state-of-the-art AI models for speech recognition, speaker diarization, and audio intelligence. Their API powers the core transcription engine in TranscribeOne.

Key capabilities used:
- **Speech-to-Text** - Industry-leading accuracy for converting audio to text
- **Speaker Diarization** - Automatic detection and labeling of different speakers
- **Speech Understanding** - AI-powered speaker identification using contextual cues

[Sign up for a free AssemblyAI API key](https://www.assemblyai.com/dashboard/signup) to get started.

---

## Supported Formats

| Type | Formats |
|------|---------|
| **Audio** | .mp3, .wav, .m4a, .flac, .ogg, .wma, .webm |
| **Video** | .mp4, .mov, .avi, .mkv, .webm, .flv, .wmv, .m4v |

Video support requires [ffmpeg](https://ffmpeg.org) (`brew install ffmpeg`).

---

## Project Structure

```
transcribeone.py        # Core library and CLI tool
transcribeone_gui.py    # macOS GUI application
test_transcribeone.py   # Test suite (65 tests)
TranscribeOne.spec      # PyInstaller build configuration
build_app.sh            # Build script for .app and .dmg
requirements.txt        # Python dependencies
```

---

## License

TranscribeOne is released under the [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/) license (Public Domain). You are free to use, modify, and distribute it without restriction.

---

## Links

- [GitHub Repository](https://github.com/jmilbery/TranscribeOne)
- [AssemblyAI](https://www.assemblyai.com)
- [AssemblyAI Documentation](https://www.assemblyai.com/docs)
- [Get an API Key](https://www.assemblyai.com/dashboard/signup)
