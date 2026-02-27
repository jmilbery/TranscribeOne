# TranscribeOne

A macOS desktop app for transcribing audio and video files with automatic speaker labels, powered by [AssemblyAI](https://www.assemblyai.com).

**[View the project site](https://jmilbery.github.io/TranscribeOne)**

## Features

- **Speaker-labeled transcription** — automatically detects and labels multiple speakers
- **Speaker identification** — enter expected names and let AI match them to voices
- **Audio & video support** — MP3, WAV, M4A, FLAC, MP4, MOV, AVI, MKV, and more
- **Built-in audio player** — play/pause, stop, seek, and adjustable speed (0.5x–2.0x)
- **Drag and drop** — drop files from Finder directly onto the app
- **Auto-save** — transcripts saved automatically as `<filename>-transcript.txt`
- **CLI mode** — also works as a command-line tool

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the GUI
export ASSEMBLYAI_API_KEY="your-key-here"
python transcribeone_gui.py

# Or use the CLI
./transcribeone.py recording.mp3
```

## Build the Mac App

```bash
bash build_app.sh
# Creates: dist/TranscribeOne.app and dist/TranscribeOne-1.0.0.dmg
```

## Requirements

- macOS 13+
- Python 3.10+
- [AssemblyAI API key](https://www.assemblyai.com/dashboard/signup) (free tier available)
- [ffmpeg](https://ffmpeg.org) (optional, for video support): `brew install ffmpeg`

## How It Works

TranscribeOne uses the [AssemblyAI](https://www.assemblyai.com) speech-to-text API for transcription and speaker diarization. Audio is uploaded, transcribed with speaker labels, and optionally matched to provided speaker names using AssemblyAI's Speech Understanding API.

## License

[CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/) — Public Domain
