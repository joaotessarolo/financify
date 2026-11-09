from unittest.mock import Mock

from django.test import SimpleTestCase

from ..transcription import OpenAIVoiceTranscriber, TranscriptionError


class OpenAIVoiceTranscriberTests(SimpleTestCase):
    def test_transcribes_audio_with_configured_model(self):
        client = Mock()
        client.audio.transcriptions.create.return_value = "gastei 40 no mercado"
        transcriber = OpenAIVoiceTranscriber(
            api_key="test-key",
            model="test-transcribe",
            timeout=5,
            client=client,
        )

        result = transcriber.transcribe(audio=b"ogg", mime_type="audio/ogg")

        self.assertEqual(result, "gastei 40 no mercado")
        self.assertEqual(
            client.audio.transcriptions.create.call_args.kwargs["model"],
            "test-transcribe",
        )

    def test_rejects_empty_transcription(self):
        client = Mock()
        client.audio.transcriptions.create.return_value = "  "
        transcriber = OpenAIVoiceTranscriber(
            api_key="test-key", model="test", timeout=5, client=client
        )

        with self.assertRaises(TranscriptionError):
            transcriber.transcribe(audio=b"ogg", mime_type="audio/ogg")
