# CLAUDE.md

## Project Overview

TranscribeOne is a minimal CLI tool that transcribes audio files with speaker labeling using the AssemblyAI API. It's a single-file Python 3 application.

## Tech Stack

- **Language:** Python 3
- **API:** AssemblyAI (via `assemblyai` Python SDK)
- **License:** CC0 1.0 Universal (Public Domain)

## Project Structure

```
transcribeone.py   # Entire application (single file)
README.md          # Project readme
LICENSE            # CC0 1.0 license
```

## Running

```bash
export ASSEMBLYAI_API_KEY="your-key"
./transcribeone.py <audio_file>
./transcribeone.py <audio_file> > output.txt   # save transcript
```

## Dependencies

Install the only dependency with:
```bash
pip install assemblyai
```

There is no `requirements.txt` or `pyproject.toml`.

## Code Conventions

- All functions have type hints and docstrings
- Function-based architecture (no classes): `load_api_key()`, `parse_args()`, `transcribe_audio()`, `main()`
- API key is read from the `ASSEMBLYAI_API_KEY` environment variable
- Output format: `Speaker <number>: <text>` (one line per utterance)
- Errors are printed to stderr via `sys.exit()`

## Notes

- No test suite exists
- `.gitignore` excludes `*.txt` and `*.mp3` files (transcripts and audio)
- No build step required — run the script directly
