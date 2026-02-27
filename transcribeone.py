#!/usr/bin/env python3

"""
TranscribeOne
-------------
Simple CLI tool for transcribing audio files using AssemblyAI,
with speaker labeling enabled.
"""

import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import assemblyai as aai


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_FORMATS = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".webm")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TranscribeError(Exception):
    """Raised when transcription fails."""
    pass


# ---------------------------------------------------------------------------
# Core functions (reusable from CLI and GUI)
# ---------------------------------------------------------------------------

def set_api_key(api_key: str) -> None:
    """Set the AssemblyAI API key. Raises ValueError if empty."""
    if not api_key:
        raise ValueError("API key cannot be empty.")
    aai.settings.api_key = api_key


def validate_audio_file(audio_file: str) -> None:
    """Validate that the audio file exists, is readable, non-empty, and a supported format.

    Raises ValueError with a user-friendly message on failure.
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


def run_transcription(audio_file: str) -> tuple[str, list[tuple[str, str]]]:
    """Transcribe audio and return (transcript_id, [(speaker, text), ...]).

    Raises TranscribeError on API failure.
    """
    config = aai.TranscriptionConfig(speaker_labels=True)
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_file, config)

    if transcript.status == aai.TranscriptStatus.error:
        raise TranscribeError(f"Transcription failed: {transcript.error}")

    if not transcript.utterances:
        return (transcript.id, [])

    results = [(u.speaker, u.text) for u in transcript.utterances]
    return (transcript.id, results)


def identify_speakers(
    transcript_id: str,
    api_key: str,
    speaker_type: str = "name",
    known_values: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Call the Speech Understanding API to identify speakers.

    Returns [(speaker_name, text), ...] with real names/roles instead of
    generic labels like 'A', 'B'.  Returns an empty list on failure so
    callers can fall back to the original labels.
    """
    url = "https://llm-gateway.assemblyai.com/v1/understanding"

    speaker_id_config: dict = {"speaker_type": speaker_type}
    if known_values:
        speaker_id_config["known_values"] = known_values

    payload = {
        "transcript_id": transcript_id,
        "speech_understanding": {
            "request": {
                "speaker_identification": speaker_id_config,
            }
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Authorization", api_key)
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, json.JSONDecodeError):
        return []

    try:
        utterances = body["speech_understanding"]["response"]["speaker_identification"]["utterances"]
        return [(u["speaker"], u["text"]) for u in utterances]
    except (KeyError, TypeError):
        return []


# ---------------------------------------------------------------------------
# CLI functions
# ---------------------------------------------------------------------------

def load_api_key() -> None:
    """
    Load the AssemblyAI API key from the environment.
    """
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        print("Error: ASSEMBLYAI_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    aai.settings.api_key = api_key


def parse_args() -> str:
    """
    Parse command-line arguments and return the audio file path.
    """
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <audio_file> > output.txt", file=sys.stderr)
        sys.exit(1)

    audio_file = sys.argv[1]

    try:
        validate_audio_file(audio_file)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    return audio_file


def transcribe_audio(audio_file: str) -> None:
    """
    Transcribe the given audio file and print speaker-labeled output.
    """
    config = aai.TranscriptionConfig(
        speaker_labels=True,
    )

    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_file, config)

    if transcript.status == aai.TranscriptStatus.error:
        print(f"Error: Transcription failed: {transcript.error}", file=sys.stderr)
        sys.exit(1)

    if not transcript.utterances:
        print("No speech detected.")
        return

    for utterance in transcript.utterances:
        print(f"Speaker {utterance.speaker}: {utterance.text}")


def main() -> None:
    """
    Program entry point.
    """
    audio_file = parse_args()
    load_api_key()
    transcribe_audio(audio_file)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)