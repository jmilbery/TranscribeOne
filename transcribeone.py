#!/usr/bin/env python3

"""
TranscribeOne
-------------
Simple CLI tool for transcribing audio files using AssemblyAI,
with speaker labeling enabled.
"""

import os
import sys
import assemblyai as aai


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

    if not os.path.exists(audio_file):
        print(f"Error: File not found: {audio_file}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(audio_file):
        print(f"Error: Not a file: {audio_file}", file=sys.stderr)
        sys.exit(1)

    if not os.access(audio_file, os.R_OK):
        print(f"Error: Permission denied: {audio_file}", file=sys.stderr)
        sys.exit(1)

    if os.path.getsize(audio_file) == 0:
        print(f"Error: File is empty: {audio_file}", file=sys.stderr)
        sys.exit(1)

    supported = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".webm")
    if not audio_file.lower().endswith(supported):
        print(f"Error: Unsupported audio format: {audio_file}", file=sys.stderr)
        print(f"Supported formats: {', '.join(supported)}", file=sys.stderr)
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