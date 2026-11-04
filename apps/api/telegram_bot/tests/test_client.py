import io
import json
import logging
import socket
import traceback
from unittest.mock import MagicMock, patch
import urllib.error

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from ..client import (
    HttpTelegramClient,
    TelegramAPIError,
    TelegramClientError,
    TelegramInvalidResponseError,
    TelegramUnavailableError,
    get_telegram_client,
)

BOT_TOKEN = "123456:SECRET-BOT-TOKEN"
URLOPEN = "telegram_bot.client.urllib.request.urlopen"


def _response(body, status=200):
    response = MagicMock()
    response.status = status
    response.read.return_value = (
        body if isinstance(body, bytes) else json.dumps(body).encode()
    )
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def _http_error(status, body=b""):
    return urllib.error.HTTPError(
        url=f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        code=status,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(body),
    )


class HttpTelegramClientTests(SimpleTestCase):
    def setUp(self):
        self.client = HttpTelegramClient(bot_token=BOT_TOKEN, timeout_seconds=5)

    def _assert_no_secret(self, exc: BaseException):
        rendered = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        self.assertNotIn(BOT_TOKEN, rendered)
        self.assertNotIn("SECRET-BOT-TOKEN", rendered)
        self.assertIsNone(exc.__cause__)
        self.assertTrue(exc.__context__ is None or exc.__suppress_context__)

    def test_send_message_success_posts_json_with_timeout(self):
        with patch(
            URLOPEN,
            return_value=_response({"ok": True, "result": {"message_id": 42}}),
        ) as mock_urlopen:
            message_id = self.client.send_message(chat_id=123, text="Olá")

        self.assertEqual(message_id, 42)
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(mock_urlopen.call_args.kwargs["timeout"], 5)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            request.full_url,
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        )
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(
            json.loads(request.data), {"chat_id": 123, "text": "Olá"}
        )

    def test_send_message_truncates_to_telegram_limit(self):
        with patch(
            URLOPEN,
            return_value=_response({"ok": True, "result": {"message_id": 1}}),
        ) as mock_urlopen:
            self.client.send_message(chat_id=1, text="x" * 5000)

        sent = json.loads(mock_urlopen.call_args.args[0].data)
        self.assertEqual(len(sent["text"]), 4096)

    def test_empty_text_is_rejected_without_request(self):
        with patch(URLOPEN) as mock_urlopen:
            with self.assertRaises(ValueError):
                self.client.send_message(chat_id=1, text="")
        mock_urlopen.assert_not_called()

    def test_timeout_raises_unavailable(self):
        for timeout_exc in (TimeoutError("timed out"), socket.timeout("t")):
            with self.subTest(exc=type(timeout_exc).__name__):
                with patch(URLOPEN, side_effect=timeout_exc):
                    with self.assertRaises(TelegramUnavailableError) as ctx:
                        self.client.send_message(chat_id=1, text="hi")
                self.assertIn("timed out", str(ctx.exception))
                self._assert_no_secret(ctx.exception)

    def test_network_error_raises_unavailable_without_url(self):
        url_error = urllib.error.URLError(
            f"failed https://api.telegram.org/bot{BOT_TOKEN}"
        )
        with patch(URLOPEN, side_effect=url_error):
            with self.assertRaises(TelegramUnavailableError) as ctx:
                self.client.send_message(chat_id=1, text="hi")
        self._assert_no_secret(ctx.exception)

    def test_server_errors_and_rate_limit_raise_unavailable(self):
        for status_code in (429, 500, 502, 503):
            with self.subTest(status=status_code):
                with patch(URLOPEN, side_effect=_http_error(status_code)):
                    with self.assertRaises(TelegramUnavailableError) as ctx:
                        self.client.send_message(chat_id=1, text="hi")
                self.assertIn(str(status_code), str(ctx.exception))
                self._assert_no_secret(ctx.exception)

    def test_client_errors_raise_api_error_with_status(self):
        body = json.dumps(
            {"ok": False, "error_code": 403, "description": "Forbidden"}
        ).encode()
        for status_code in (400, 401, 403):
            with self.subTest(status=status_code):
                with patch(URLOPEN, side_effect=_http_error(status_code, body)):
                    with self.assertRaises(TelegramAPIError) as ctx:
                        self.client.send_message(chat_id=1, text="hi")
                self.assertEqual(ctx.exception.status_code, status_code)
                self._assert_no_secret(ctx.exception)

    def test_ok_false_with_200_raises_api_error(self):
        with patch(URLOPEN, return_value=_response({"ok": False})):
            with self.assertRaises(TelegramAPIError):
                self.client.send_message(chat_id=1, text="hi")

    def test_invalid_responses_raise_invalid_response_error(self):
        invalid_bodies = (
            b"<html>not json</html>",
            b"",
            json.dumps([1, 2]).encode(),
            json.dumps({"result": {}}).encode(),
            json.dumps({"ok": True}).encode(),
            json.dumps({"ok": True, "result": {}}).encode(),
            json.dumps({"ok": True, "result": {"message_id": "1"}}).encode(),
            json.dumps({"ok": True, "result": {"message_id": True}}).encode(),
        )
        for body in invalid_bodies:
            with self.subTest(body=body):
                with patch(URLOPEN, return_value=_response(body)):
                    with self.assertRaises(TelegramInvalidResponseError) as ctx:
                        self.client.send_message(chat_id=1, text="hi")
                self._assert_no_secret(ctx.exception)

    def test_all_errors_share_base_class(self):
        for exc_type in (
            TelegramUnavailableError,
            TelegramAPIError,
            TelegramInvalidResponseError,
        ):
            self.assertTrue(issubclass(exc_type, TelegramClientError))

    def test_repr_does_not_expose_token(self):
        self.assertNotIn(BOT_TOKEN, repr(self.client))
        self.assertNotIn(BOT_TOKEN, str(self.client))

    def test_client_does_not_log_token_or_message(self):
        logger = logging.getLogger("telegram_bot")
        with patch(URLOPEN, side_effect=_http_error(500)):
            with self.assertLogs(logger, level="DEBUG") as logs:
                logger.debug("sentinel")
                with self.assertRaises(TelegramUnavailableError):
                    self.client.send_message(chat_id=1, text="private text")
        for line in logs.output:
            self.assertNotIn(BOT_TOKEN, line)
            self.assertNotIn("private text", line)

    def test_constructor_validates_configuration(self):
        with self.assertRaises(ImproperlyConfigured):
            HttpTelegramClient(bot_token="", timeout_seconds=5)
        for invalid_timeout in (0, -1):
            with self.assertRaises(ImproperlyConfigured):
                HttpTelegramClient(
                    bot_token=BOT_TOKEN, timeout_seconds=invalid_timeout
                )


class GetTelegramClientTests(SimpleTestCase):
    @override_settings(
        TELEGRAM_BOT_TOKEN=BOT_TOKEN, TELEGRAM_API_TIMEOUT_SECONDS=7.5
    )
    def test_builds_http_client_from_settings(self):
        client = get_telegram_client()
        self.assertIsInstance(client, HttpTelegramClient)
        self.assertIn("7.5", repr(client))

    @override_settings(TELEGRAM_BOT_TOKEN="")
    def test_missing_token_raises_improperly_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            get_telegram_client()
