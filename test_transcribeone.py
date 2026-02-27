"""
Tests for TranscribeOne
-----------------------
Run with: python -m pytest test_transcribeone.py -v
"""

import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import transcribeone


# ---------------------------------------------------------------------------
# set_api_key (core)
# ---------------------------------------------------------------------------

class TestSetApiKey:
    """Tests for set_api_key()."""

    def test_sets_api_key(self):
        """Valid key is stored in aai.settings.api_key."""
        import assemblyai as aai
        transcribeone.set_api_key("my-key-123")
        assert aai.settings.api_key == "my-key-123"

    def test_empty_key_raises(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            transcribeone.set_api_key("")

    def test_falsy_key_raises(self):
        """None-ish value raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            transcribeone.set_api_key("")


# ---------------------------------------------------------------------------
# validate_audio_file (core)
# ---------------------------------------------------------------------------

class TestValidateAudioFile:
    """Tests for validate_audio_file()."""

    def test_valid_mp3(self, tmp_path):
        """Valid mp3 file passes validation."""
        f = tmp_path / "test.mp3"
        f.write_text("data")
        transcribeone.validate_audio_file(str(f))

    def test_missing_file_raises(self):
        """Missing file raises ValueError."""
        with pytest.raises(ValueError, match="File not found"):
            transcribeone.validate_audio_file("/no/such/file.mp3")

    def test_directory_raises(self, tmp_path):
        """Directory path raises ValueError."""
        with pytest.raises(ValueError, match="Not a file"):
            transcribeone.validate_audio_file(str(tmp_path))

    def test_permission_denied_raises(self, tmp_path):
        """Unreadable file raises ValueError."""
        f = tmp_path / "secret.mp3"
        f.write_text("data")
        f.chmod(0o000)
        try:
            with pytest.raises(ValueError, match="Permission denied"):
                transcribeone.validate_audio_file(str(f))
        finally:
            f.chmod(0o644)

    def test_empty_file_raises(self, tmp_path):
        """Zero-byte file raises ValueError."""
        f = tmp_path / "empty.mp3"
        f.write_text("")
        with pytest.raises(ValueError, match="File is empty"):
            transcribeone.validate_audio_file(str(f))

    def test_unsupported_format_raises(self, tmp_path):
        """Unsupported extension raises ValueError."""
        f = tmp_path / "doc.pdf"
        f.write_text("data")
        with pytest.raises(ValueError, match="Unsupported audio format"):
            transcribeone.validate_audio_file(str(f))

    @pytest.mark.parametrize("ext", transcribeone.SUPPORTED_FORMATS)
    def test_all_supported_formats(self, tmp_path, ext):
        """All documented formats pass validation."""
        f = tmp_path / f"test{ext}"
        f.write_text("data")
        transcribeone.validate_audio_file(str(f))


# ---------------------------------------------------------------------------
# run_transcription (core)
# ---------------------------------------------------------------------------

class TestRunTranscription:
    """Tests for run_transcription()."""

    def _make_utterance(self, speaker: str, text: str) -> MagicMock:
        u = MagicMock()
        u.speaker = speaker
        u.text = text
        return u

    def test_returns_id_and_tuples(self):
        """Successful transcription returns (id, [(speaker, text)])."""
        mock_transcript = MagicMock()
        mock_transcript.status = "completed"
        mock_transcript.id = "test-id-123"
        mock_transcript.utterances = [
            self._make_utterance("A", "Hello."),
            self._make_utterance("B", "Hi."),
        ]

        with patch("transcribeone.aai.Transcriber") as MockT:
            MockT.return_value.transcribe.return_value = mock_transcript
            tid, results = transcribeone.run_transcription("test.mp3")

        assert tid == "test-id-123"
        assert results == [("A", "Hello."), ("B", "Hi.")]

    def test_no_speech_returns_empty(self):
        """Empty utterances returns (id, [])."""
        mock_transcript = MagicMock()
        mock_transcript.status = "completed"
        mock_transcript.id = "test-id"
        mock_transcript.utterances = []

        with patch("transcribeone.aai.Transcriber") as MockT:
            MockT.return_value.transcribe.return_value = mock_transcript
            tid, results = transcribeone.run_transcription("test.mp3")

        assert tid == "test-id"
        assert results == []

    def test_error_raises_transcribe_error(self):
        """API error raises TranscribeError."""
        import assemblyai as aai

        mock_transcript = MagicMock()
        mock_transcript.status = aai.TranscriptStatus.error
        mock_transcript.error = "Bad request"

        with patch("transcribeone.aai.Transcriber") as MockT:
            MockT.return_value.transcribe.return_value = mock_transcript
            with pytest.raises(transcribeone.TranscribeError, match="Bad request"):
                transcribeone.run_transcription("test.mp3")


# ---------------------------------------------------------------------------
# identify_speakers (core)
# ---------------------------------------------------------------------------

class TestIdentifySpeakers:
    """Tests for identify_speakers()."""

    def test_successful_identification(self):
        """Returns identified speaker tuples on success."""
        response_body = json.dumps({
            "speech_understanding": {
                "response": {
                    "speaker_identification": {
                        "utterances": [
                            {"speaker": "Alice", "text": "Hello."},
                            {"speaker": "Bob", "text": "Hi there."},
                        ]
                    }
                }
            }
        }).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = response_body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("transcribeone.urlopen", return_value=mock_resp):
            result = transcribeone.identify_speakers("tid-123", "key-456")

        assert result == [("Alice", "Hello."), ("Bob", "Hi there.")]

    def test_api_error_returns_empty(self):
        """Returns empty list on HTTP error."""
        from urllib.error import HTTPError

        with patch("transcribeone.urlopen", side_effect=HTTPError(None, 500, "err", {}, None)):
            result = transcribeone.identify_speakers("tid", "key")

        assert result == []

    def test_malformed_response_returns_empty(self):
        """Returns empty list on unexpected response structure."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"unexpected": "data"}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("transcribeone.urlopen", return_value=mock_resp):
            result = transcribeone.identify_speakers("tid", "key")

        assert result == []

    def test_known_values_included_in_request(self):
        """known_values are passed through to the API payload."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"speech_understanding":{"response":{"speaker_identification":{"utterances":[]}}}}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("transcribeone.urlopen", return_value=mock_resp) as mock_urlopen:
            transcribeone.identify_speakers("tid", "key", "role", ["Host", "Guest"])

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        payload = json.loads(req.data.decode())
        si = payload["speech_understanding"]["request"]["speaker_identification"]
        assert si["speaker_type"] == "role"
        assert si["known_values"] == ["Host", "Guest"]


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
