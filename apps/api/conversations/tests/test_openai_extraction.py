from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from ..ai_extraction import AITransactionExtractor
from ..extraction import (
    DeterministicTransactionExtractor,
    get_transaction_extractor,
)
from ..openai_extraction import (
    OpenAIStructuredTransactionProvider,
    OpenAITransactionCandidate,
)


class OpenAIStructuredTransactionProviderTests(SimpleTestCase):
    def test_maps_parsed_response_to_provider_candidate(self):
        client = Mock()
        client.responses.parse.return_value = SimpleNamespace(
            output_parsed=OpenAITransactionCandidate(
                supported=True,
                kind="EXPENSE",
                amount="42.50",
                description="Mercado",
                account_name="Nubank",
                category_name="Mercado",
            )
        )
        provider = OpenAIStructuredTransactionProvider(
            api_key="test-key",
            model="test-model",
            timeout=3,
            client=client,
        )

        candidate = provider.extract("torrei 42,50 no mercado")

        self.assertTrue(candidate.supported)
        self.assertEqual(candidate.kind, "EXPENSE")
        self.assertEqual(candidate.amount, "42.50")
        self.assertEqual(candidate.description, "Mercado")
        self.assertEqual(candidate.account_name, "Nubank")
        self.assertEqual(candidate.category_name, "Mercado")
        call = client.responses.parse.call_args.kwargs
        self.assertEqual(call["model"], "test-model")
        self.assertEqual(call["input"], "torrei 42,50 no mercado")
        self.assertIs(call["text_format"], OpenAITransactionCandidate)
        self.assertFalse(call["store"])


class TransactionExtractorFactoryTests(SimpleTestCase):
    @override_settings(TRANSACTION_EXTRACTOR_BACKEND="deterministic")
    def test_uses_deterministic_backend_by_default(self):
        self.assertIsInstance(
            get_transaction_extractor(), DeterministicTransactionExtractor
        )

    @override_settings(
        TRANSACTION_EXTRACTOR_BACKEND="openai",
        OPENAI_API_KEY="test-key",
        OPENAI_TRANSACTION_MODEL="test-model",
        OPENAI_API_TIMEOUT_SECONDS=4,
    )
    @patch("conversations.openai_extraction.OpenAIStructuredTransactionProvider")
    def test_builds_openai_extractor_from_settings(self, provider_class):
        extractor = get_transaction_extractor()

        self.assertIsInstance(extractor, AITransactionExtractor)
        provider_class.assert_called_once_with(
            api_key="test-key",
            model="test-model",
            timeout=4,
        )

    @override_settings(
        TRANSACTION_EXTRACTOR_BACKEND="openai",
        OPENAI_API_KEY="",
    )
    def test_rejects_openai_backend_without_api_key(self):
        with self.assertRaises(ImproperlyConfigured):
            get_transaction_extractor()

    @override_settings(TRANSACTION_EXTRACTOR_BACKEND="unknown")
    def test_rejects_unknown_backend(self):
        with self.assertRaises(ImproperlyConfigured):
            get_transaction_extractor()
