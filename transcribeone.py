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
        print("Error: ASSEMBLYAI_API_KEY environment variable is not set.")
        sys.exit(1)

    aai.settings.api_key = api_key


def parse_args() -> str:
    """
    Parse command-line arguments and return the audio file path.
    """
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <audio_file> > output.txt")
        sys.exit(1)

    return sys.argv[1]


def transcribe_audio(audio_file: str) -> None:
    """
    Transcribe the given audio file and print speaker-labeled output.
    """
    config = aai.TranscriptionConfig(
        speaker_labels=True,
    )

    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_file, config)

    if not transcript.utterances:
        print("No speech detected.")
        return

    for utterance in transcript.utterances:
        print(f"Speaker {utterance.speaker}: {utterance.text}")


def main() -> None:
    """
    Program entry point.
    """
    load_api_key()
    audio_file = parse_args()
    transcribe_audio(audio_file)


if __name__ == "__main__":
    main()