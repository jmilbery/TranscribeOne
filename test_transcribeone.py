"""
Tests for TranscribeOne
-----------------------
Run with: python -m pytest test_transcribeone.py -v
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import transcribeone


# ---------------------------------------------------------------------------
# load_api_key
# ---------------------------------------------------------------------------

class TestLoadApiKey:
    """Tests for load_api_key()."""

    def test_missing_api_key_exits(self):
        """Exit with error when ASSEMBLYAI_API_KEY is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure the key is absent
            os.environ.pop("ASSEMBLYAI_API_KEY", None)
            with pytest.raises(SystemExit) as exc_info:
                transcribeone.load_api_key()
            assert exc_info.value.code == 1

    def test_empty_api_key_exits(self):
        """Exit with error when ASSEMBLYAI_API_KEY is empty string."""
        with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": ""}):
            with pytest.raises(SystemExit) as exc_info:
                transcribeone.load_api_key()
            assert exc_info.value.code == 1

    def test_valid_api_key_sets_setting(self):
        """A valid key is stored in aai.settings.api_key."""
        with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key-123"}):
            import assemblyai as aai
            transcribeone.load_api_key()
            assert aai.settings.api_key == "test-key-123"

    def test_missing_key_message_on_stderr(self, capsys):
        """Error message for missing key is printed to stderr."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ASSEMBLYAI_API_KEY", None)
            with pytest.raises(SystemExit):
                transcribeone.load_api_key()
            captured = capsys.readouterr()
            assert "ASSEMBLYAI_API_KEY" in captured.err
            assert captured.out == ""


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------

class TestParseArgs:
    """Tests for parse_args()."""

    def test_no_arguments_exits(self):
        """Exit when no audio file argument is provided."""
        with patch.object(sys, "argv", ["transcribeone.py"]):
            with pytest.raises(SystemExit) as exc_info:
                transcribeone.parse_args()
            assert exc_info.value.code == 1

    def test_too_many_arguments_exits(self):
        """Exit when more than one audio file argument is provided."""
        with patch.object(sys, "argv", ["transcribeone.py", "a.mp3", "b.mp3"]):
            with pytest.raises(SystemExit) as exc_info:
                transcribeone.parse_args()
            assert exc_info.value.code == 1

    def test_usage_message_on_stderr(self, capsys):
        """Usage message goes to stderr, not stdout."""
        with patch.object(sys, "argv", ["transcribeone.py"]):
            with pytest.raises(SystemExit):
                transcribeone.parse_args()
            captured = capsys.readouterr()
            assert "Usage:" in captured.err
            assert captured.out == ""

    def test_file_not_found_exits(self):
        """Exit when the audio file does not exist."""
        with patch.object(sys, "argv", ["transcribeone.py", "/nonexistent/audio.mp3"]):
            with pytest.raises(SystemExit) as exc_info:
                transcribeone.parse_args()
            assert exc_info.value.code == 1

    def test_file_not_found_message(self, capsys):
        """Error message for missing file is friendly and on stderr."""
        with patch.object(sys, "argv", ["transcribeone.py", "/nonexistent/audio.mp3"]):
            with pytest.raises(SystemExit):
                transcribeone.parse_args()
            captured = capsys.readouterr()
            assert "File not found" in captured.err
            assert "/nonexistent/audio.mp3" in captured.err
            assert captured.out == ""

    def test_directory_instead_of_file_exits(self, tmp_path):
        """Exit when path points to a directory, not a file."""
        with patch.object(sys, "argv", ["transcribeone.py", str(tmp_path)]):
            with pytest.raises(SystemExit) as exc_info:
                transcribeone.parse_args()
            assert exc_info.value.code == 1

    def test_directory_error_message(self, tmp_path, capsys):
        """Error message for directory path is friendly and on stderr."""
        with patch.object(sys, "argv", ["transcribeone.py", str(tmp_path)]):
            with pytest.raises(SystemExit):
                transcribeone.parse_args()
            captured = capsys.readouterr()
            assert "Not a file" in captured.err
            assert captured.out == ""

    def test_permission_denied_exits(self, tmp_path):
        """Exit when the audio file is not readable."""
        audio_file = tmp_path / "secret.mp3"
        audio_file.write_text("fake audio")
        audio_file.chmod(0o000)
        try:
            with patch.object(sys, "argv", ["transcribeone.py", str(audio_file)]):
                with pytest.raises(SystemExit) as exc_info:
                    transcribeone.parse_args()
                assert exc_info.value.code == 1
        finally:
            audio_file.chmod(0o644)

    def test_permission_denied_message(self, tmp_path, capsys):
        """Error message for unreadable file is friendly and on stderr."""
        audio_file = tmp_path / "secret.mp3"
        audio_file.write_text("fake audio")
        audio_file.chmod(0o000)
        try:
            with patch.object(sys, "argv", ["transcribeone.py", str(audio_file)]):
                with pytest.raises(SystemExit):
                    transcribeone.parse_args()
                captured = capsys.readouterr()
                assert "Permission denied" in captured.err
                assert captured.out == ""
        finally:
            audio_file.chmod(0o644)

    def test_empty_file_exits(self, tmp_path):
        """Exit when the audio file is empty (zero bytes)."""
        audio_file = tmp_path / "empty.mp3"
        audio_file.write_text("")
        with patch.object(sys, "argv", ["transcribeone.py", str(audio_file)]):
            with pytest.raises(SystemExit) as exc_info:
                transcribeone.parse_args()
            assert exc_info.value.code == 1

    def test_empty_file_message(self, tmp_path, capsys):
        """Error message for empty file is friendly and on stderr."""
        audio_file = tmp_path / "empty.mp3"
        audio_file.write_text("")
        with patch.object(sys, "argv", ["transcribeone.py", str(audio_file)]):
            with pytest.raises(SystemExit):
                transcribeone.parse_args()
            captured = capsys.readouterr()
            assert "File is empty" in captured.err
            assert captured.out == ""

    def test_unsupported_format_exits(self, tmp_path):
        """Exit when file has an unsupported extension."""
        bad_file = tmp_path / "document.pdf"
        bad_file.write_text("fake")
        with patch.object(sys, "argv", ["transcribeone.py", str(bad_file)]):
            with pytest.raises(SystemExit) as exc_info:
                transcribeone.parse_args()
            assert exc_info.value.code == 1

    def test_unsupported_format_message(self, tmp_path, capsys):
        """Error lists supported formats on stderr."""
        bad_file = tmp_path / "document.pdf"
        bad_file.write_text("fake")
        with patch.object(sys, "argv", ["transcribeone.py", str(bad_file)]):
            with pytest.raises(SystemExit):
                transcribeone.parse_args()
            captured = capsys.readouterr()
            assert "Unsupported audio format" in captured.err
            assert "Supported formats:" in captured.err
            assert ".mp3" in captured.err
            assert captured.out == ""

    @pytest.mark.parametrize("ext", [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".webm"])
    def test_supported_formats_accepted(self, tmp_path, ext):
        """All documented audio formats are accepted."""
        audio_file = tmp_path / f"test{ext}"
        audio_file.write_text("fake audio")
        with patch.object(sys, "argv", ["transcribeone.py", str(audio_file)]):
            result = transcribeone.parse_args()
            assert result == str(audio_file)

    def test_uppercase_extension_accepted(self, tmp_path):
        """File extensions are case-insensitive."""
        audio_file = tmp_path / "test.MP3"
        audio_file.write_text("fake audio")
        with patch.object(sys, "argv", ["transcribeone.py", str(audio_file)]):
            result = transcribeone.parse_args()
            assert result == str(audio_file)

    def test_mixed_case_extension_accepted(self, tmp_path):
        """Mixed-case extensions like .WaV are accepted."""
        audio_file = tmp_path / "test.WaV"
        audio_file.write_text("fake audio")
        with patch.object(sys, "argv", ["transcribeone.py", str(audio_file)]):
            result = transcribeone.parse_args()
            assert result == str(audio_file)


# ---------------------------------------------------------------------------
# transcribe_audio
# ---------------------------------------------------------------------------

class TestTranscribeAudio:
    """Tests for transcribe_audio()."""

    def _make_utterance(self, speaker: str, text: str) -> MagicMock:
        """Helper to create a mock utterance."""
        u = MagicMock()
        u.speaker = speaker
        u.text = text
        return u

    def test_successful_transcription(self, capsys):
        """Successful transcription prints speaker-labeled lines to stdout."""
        mock_transcript = MagicMock()
        mock_transcript.status = "completed"
        mock_transcript.utterances = [
            self._make_utterance("A", "Hello there."),
            self._make_utterance("B", "Hi, how are you?"),
        ]

        with patch("transcribeone.aai.Transcriber") as MockTranscriber:
            MockTranscriber.return_value.transcribe.return_value = mock_transcript
            transcribeone.transcribe_audio("test.mp3")

        captured = capsys.readouterr()
        assert "Speaker A: Hello there." in captured.out
        assert "Speaker B: Hi, how are you?" in captured.out
        assert captured.err == ""

    def test_no_speech_detected(self, capsys):
        """Print friendly message when no utterances are returned."""
        mock_transcript = MagicMock()
        mock_transcript.status = "completed"
        mock_transcript.utterances = []

        with patch("transcribeone.aai.Transcriber") as MockTranscriber:
            MockTranscriber.return_value.transcribe.return_value = mock_transcript
            transcribeone.transcribe_audio("test.mp3")

        captured = capsys.readouterr()
        assert "No speech detected." in captured.out

    def test_none_utterances(self, capsys):
        """Handle None utterances gracefully."""
        mock_transcript = MagicMock()
        mock_transcript.status = "completed"
        mock_transcript.utterances = None

        with patch("transcribeone.aai.Transcriber") as MockTranscriber:
            MockTranscriber.return_value.transcribe.return_value = mock_transcript
            transcribeone.transcribe_audio("test.mp3")

        captured = capsys.readouterr()
        assert "No speech detected." in captured.out

    def test_transcription_error_exits(self):
        """Exit with code 1 when AssemblyAI returns an error status."""
        import assemblyai as aai

        mock_transcript = MagicMock()
        mock_transcript.status = aai.TranscriptStatus.error
        mock_transcript.error = "Authentication error: invalid API key"

        with patch("transcribeone.aai.Transcriber") as MockTranscriber:
            MockTranscriber.return_value.transcribe.return_value = mock_transcript
            with pytest.raises(SystemExit) as exc_info:
                transcribeone.transcribe_audio("test.mp3")
            assert exc_info.value.code == 1

    def test_transcription_error_message_on_stderr(self, capsys):
        """Transcription error message goes to stderr with details."""
        import assemblyai as aai

        mock_transcript = MagicMock()
        mock_transcript.status = aai.TranscriptStatus.error
        mock_transcript.error = "Authentication error: invalid API key"

        with patch("transcribeone.aai.Transcriber") as MockTranscriber:
            MockTranscriber.return_value.transcribe.return_value = mock_transcript
            with pytest.raises(SystemExit):
                transcribeone.transcribe_audio("test.mp3")

        captured = capsys.readouterr()
        assert "Transcription failed" in captured.err
        assert "invalid API key" in captured.err
        assert captured.out == ""

    def test_multiple_speakers(self, capsys):
        """Handle transcription with many speakers."""
        mock_transcript = MagicMock()
        mock_transcript.status = "completed"
        mock_transcript.utterances = [
            self._make_utterance("A", "First speaker."),
            self._make_utterance("B", "Second speaker."),
            self._make_utterance("C", "Third speaker."),
            self._make_utterance("A", "First again."),
        ]

        with patch("transcribeone.aai.Transcriber") as MockTranscriber:
            MockTranscriber.return_value.transcribe.return_value = mock_transcript
            transcribeone.transcribe_audio("test.mp3")

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 4
        assert lines[0] == "Speaker A: First speaker."
        assert lines[3] == "Speaker A: First again."


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

class TestMain:
    """Tests for main() and top-level exception handling."""

    def test_main_calls_functions_in_order(self, tmp_path):
        """main() calls load_api_key, parse_args, transcribe_audio in order."""
        call_order = []

        with patch.object(transcribeone, "load_api_key", side_effect=lambda: call_order.append("load_api_key")):
            with patch.object(transcribeone, "parse_args", side_effect=lambda: (call_order.append("parse_args"), "test.mp3")[1]):
                with patch.object(transcribeone, "transcribe_audio", side_effect=lambda f: call_order.append("transcribe_audio")):
                    transcribeone.main()

        assert call_order == ["parse_args", "load_api_key", "transcribe_audio"]

    def test_keyboard_interrupt_clean_exit(self, capsys):
        """Ctrl+C produces a friendly message, not a traceback."""
        with patch.object(transcribeone, "main", side_effect=KeyboardInterrupt):
            with pytest.raises(SystemExit) as exc_info:
                # Simulate what the __name__ == "__main__" block does
                try:
                    transcribeone.main()
                except KeyboardInterrupt:
                    print("\nInterrupted.", file=sys.stderr)
                    sys.exit(130)

            assert exc_info.value.code == 130
            captured = capsys.readouterr()
            assert "Interrupted" in captured.err
            assert captured.out == ""

    def test_unexpected_exception_clean_exit(self, capsys):
        """Unexpected errors produce a friendly message, not a traceback."""
        with patch.object(transcribeone, "main", side_effect=RuntimeError("something broke")):
            with pytest.raises(SystemExit) as exc_info:
                try:
                    transcribeone.main()
                except KeyboardInterrupt:
                    print("\nInterrupted.", file=sys.stderr)
                    sys.exit(130)
                except Exception as e:
                    print(f"Error: {e}", file=sys.stderr)
                    sys.exit(1)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "something broke" in captured.err
            assert captured.out == ""


# ---------------------------------------------------------------------------
# Integration-style tests (still mocking the API)
# ---------------------------------------------------------------------------

class TestIntegration:
    """End-to-end tests that exercise the full flow with a mocked API."""

    def test_full_happy_path(self, tmp_path, capsys):
        """Full run: valid key, valid file, successful transcription."""
        audio_file = tmp_path / "interview.mp3"
        audio_file.write_text("fake audio")

        mock_transcript = MagicMock()
        mock_transcript.status = "completed"
        utterance = MagicMock()
        utterance.speaker = "A"
        utterance.text = "This is a test."
        mock_transcript.utterances = [utterance]

        with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
            with patch.object(sys, "argv", ["transcribeone.py", str(audio_file)]):
                with patch("transcribeone.aai.Transcriber") as MockTranscriber:
                    MockTranscriber.return_value.transcribe.return_value = mock_transcript
                    transcribeone.main()

        captured = capsys.readouterr()
        assert "Speaker A: This is a test." in captured.out
        assert captured.err == ""

    def test_full_path_missing_key(self, tmp_path):
        """Full run exits cleanly when API key is missing."""
        audio_file = tmp_path / "test.mp3"
        audio_file.write_text("fake audio")

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ASSEMBLYAI_API_KEY", None)
            with patch.object(sys, "argv", ["transcribeone.py", str(audio_file)]):
                with pytest.raises(SystemExit) as exc_info:
                    transcribeone.main()
                assert exc_info.value.code == 1

    def test_full_path_missing_file(self):
        """Full run exits cleanly when audio file doesn't exist."""
        with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
            with patch.object(sys, "argv", ["transcribeone.py", "/no/such/file.mp3"]):
                with pytest.raises(SystemExit) as exc_info:
                    transcribeone.main()
                assert exc_info.value.code == 1

    def test_missing_file_caught_before_api_key(self, capsys):
        """File errors are reported even when API key is also missing."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ASSEMBLYAI_API_KEY", None)
            with patch.object(sys, "argv", ["transcribeone.py", "/no/such/file.mp3"]):
                with pytest.raises(SystemExit) as exc_info:
                    transcribeone.main()
                assert exc_info.value.code == 1
                captured = capsys.readouterr()
                assert "File not found" in captured.err

    def test_full_path_bad_format(self, tmp_path):
        """Full run exits cleanly for unsupported file format."""
        bad_file = tmp_path / "notes.txt"
        bad_file.write_text("not audio")

        with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
            with patch.object(sys, "argv", ["transcribeone.py", str(bad_file)]):
                with pytest.raises(SystemExit) as exc_info:
                    transcribeone.main()
                assert exc_info.value.code == 1
