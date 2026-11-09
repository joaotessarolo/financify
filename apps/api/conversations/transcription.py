from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from openai import OpenAI, OpenAIError


class TranscriptionError(RuntimeError):
    pass


class VoiceTranscriber(Protocol):
    def transcribe(self, *, audio: bytes, mime_type: str) -> str:
        ...


class OpenAIVoiceTranscriber:
    def __init__(self, *, api_key: str, model: str, timeout: float, client=None):
        self.model = model
        self.client = client or OpenAI(api_key=api_key, timeout=timeout)

    def transcribe(self, *, audio: bytes, mime_type: str) -> str:
        try:
            result = self.client.audio.transcriptions.create(
                model=self.model,
                file=("voice.ogg", audio, mime_type),
                response_format="text",
            )
        except OpenAIError as exc:
            raise TranscriptionError("Voice transcription failed.") from exc
        text = result if isinstance(result, str) else getattr(result, "text", "")
        text = text.strip()
        if not text:
            raise TranscriptionError("Voice transcription returned no text.")
        return text


def get_voice_transcriber() -> VoiceTranscriber:
    if not settings.OPENAI_API_KEY:
        raise ImproperlyConfigured("OPENAI_API_KEY is required for transcription.")
    return OpenAIVoiceTranscriber(
        api_key=settings.OPENAI_API_KEY,
        model=settings.OPENAI_TRANSCRIPTION_MODEL,
        timeout=settings.OPENAI_API_TIMEOUT_SECONDS,
    )
