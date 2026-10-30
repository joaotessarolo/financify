import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase


class UserRegistrationViewTests(APITestCase):
    """
    HTTP integration tests for UserRegistrationView:
        - POST valid payload returns 201 Created and creates user.
        - Response body omits password and password_confirmation.
        - POST invalid payload returns 400 Bad Request and does not create user.
        - GET is not allowed (405 Method Not Allowed).
    """

    def setUp(self):
        self.user_model = get_user_model()
        self.url = reverse("users:register")
        self.valid_payload = {
            "email": "User@Example.com",
            "password": "StrongPassword!123",
            "password_confirmation": "StrongPassword!123",
            "first_name": "João",
            "last_name": "Silva",
        }

    def test_register_user_returns_201_and_creates_user(self):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.user_model.objects.count(), 1)

        user = self.user_model.objects.get()
        self.assertEqual(user.email, "user@example.com")
        self.assertTrue(user.check_password(self.valid_payload["password"]))
        self.assertEqual(response.data["id"], str(user.id))
        self.assertEqual(response.data["email"], "user@example.com")
        self.assertEqual(response.data["first_name"], "João")
        self.assertEqual(response.data["last_name"], "Silva")
        self.assertEqual(response.data["currency"], "BRL")
        self.assertEqual(response.data["timezone"], "America/Sao_Paulo")
        self.assertNotIn("password", response.data)
        self.assertNotIn("password_confirmation", response.data)

    def test_register_with_mismatched_passwords_returns_400(self):
        payload = {
            **self.valid_payload,
            "password_confirmation": "DifferentPassword!123",
        }
        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirmation", response.data)
        self.assertEqual(self.user_model.objects.count(), 0)

    def test_register_with_duplicate_email_returns_400(self):
        self.user_model.objects.create_user(
            email="user@example.com",
            password="StrongPassword!123",
        )
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.assertEqual(response.data["email"][0].code, "unique")
        self.assertEqual(self.user_model.objects.count(), 1)

    def test_get_method_is_not_allowed(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class UserAuthenticationViewsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_model = get_user_model()
        cls.email = "user@example.com"
        cls.password = "StrongPassword!123"
        cls.user = cls.user_model.objects.create_user(
            email=cls.email,
            password=cls.password,
        )
        cls.csrf_url = reverse("auth:csrf")
        cls.login_url = reverse("auth:login")
        cls.logout_url = reverse("auth:logout")

    def setUp(self):
        self.csrf_client = APIClient(enforce_csrf_checks=True)

    def _get_csrf_token(self):
        response = self.csrf_client.get(self.csrf_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIn("csrftoken", response.cookies)
        return response.cookies["csrftoken"].value

    def test_csrf_endpoint_sets_csrf_cookie(self):
        response = self.csrf_client.get(self.csrf_url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIn("csrftoken", response.cookies)
        self.assertTrue(response.cookies["csrftoken"].value)

    def test_login_without_csrf_token_is_rejected(self):
        response = self.csrf_client.post(
            self.login_url,
            {"email": self.email, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn("sessionid", response.cookies)

    def test_login_with_csrf_token_creates_httponly_session(self):
        csrf_token = self._get_csrf_token()

        response = self.csrf_client.post(
            self.login_url,
            {"email": self.email, "password": self.password},
            format="json",
            headers={"X-CSRFToken": csrf_token},
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIn("sessionid", response.cookies)
        self.assertTrue(response.cookies["sessionid"]["httponly"])
        self.assertEqual(
            self.csrf_client.session.get("_auth_user_id"),
            str(self.user.id),
        )

    def test_login_with_invalid_credentials_returns_400(self):
        csrf_token = self._get_csrf_token()

        response = self.csrf_client.post(
            self.login_url,
            {"email": self.email, "password": "WrongPassword!123"},
            format="json",
            headers={"X-CSRFToken": csrf_token},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("sessionid", response.cookies)

    def test_logout_clears_session_and_blocks_subsequent_protected_requests(self):
        csrf_token = self._get_csrf_token()
        login_response = self.csrf_client.post(
            self.login_url,
            {"email": self.email, "password": self.password},
            format="json",
            headers={"X-CSRFToken": csrf_token},
        )
        self.assertEqual(login_response.status_code, status.HTTP_204_NO_CONTENT)

        # login() rotates the CSRF token, so read the updated cookie value
        post_login_csrf_token = self.csrf_client.cookies["csrftoken"].value

        logout_response = self.csrf_client.post(
            self.logout_url,
            headers={"X-CSRFToken": post_login_csrf_token},
        )

        self.assertEqual(logout_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNone(self.csrf_client.session.get("_auth_user_id"))

        second_logout_response = self.csrf_client.post(
            self.logout_url,
            headers={"X-CSRFToken": post_login_csrf_token},
        )
        self.assertEqual(
            second_logout_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_protected_endpoint_recognizes_authenticated_user(self):
        unauthenticated_response = self.csrf_client.post(self.logout_url)
        self.assertEqual(
            unauthenticated_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        csrf_token = self._get_csrf_token()
        self.csrf_client.post(
            self.login_url,
            {"email": self.email, "password": self.password},
            format="json",
            headers={"X-CSRFToken": csrf_token},
        )
        post_login_csrf_token = self.csrf_client.cookies["csrftoken"].value

        with patch("users.views.logout") as mock_logout:
            authenticated_response = self.csrf_client.post(
                self.logout_url,
                headers={"X-CSRFToken": post_login_csrf_token},
            )

        self.assertEqual(authenticated_response.status_code, status.HTTP_204_NO_CONTENT)
        mock_logout.assert_called_once()
        authenticated_request = mock_logout.call_args.args[0]
        self.assertEqual(authenticated_request.user, self.user)


class UserProfileViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_model = get_user_model()
        cls.url = reverse("users:me")
        cls.user = cls.user_model.objects.create_user(
            email="user@example.com",
            password="StrongPassword!123",
            first_name="João",
            last_name="Silva",
            currency="BRL",
            timezone="America/Sao_Paulo",
        )
        cls.other_user = cls.user_model.objects.create_user(
            email="other@example.com",
            password="StrongPassword!123",
            first_name="Maria",
            last_name="Souza",
        )

    def test_unauthenticated_get_returns_403(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_patch_returns_403(self):
        response = self.client.patch(
            self.url,
            {"first_name": "Novo"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_get_returns_current_user_profile(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "id": str(self.user.id),
                "email": "user@example.com",
                "first_name": "João",
                "last_name": "Silva",
                "currency": "BRL",
                "timezone": "America/Sao_Paulo",
            },
        )

    def test_profile_response_omits_password_and_admin_fields(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for forbidden_field in (
            "password",
            "is_staff",
            "is_superuser",
            "is_active",
            "groups",
            "user_permissions",
        ):
            self.assertNotIn(forbidden_field, response.data)

    def test_patch_updates_name_currency_and_timezone(self):
        self.client.force_login(self.user)

        response = self.client.patch(
            self.url,
            {
                "first_name": "Carlos",
                "last_name": "Pereira",
                "currency": "USD",
                "timezone": "UTC",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Carlos")
        self.assertEqual(self.user.last_name, "Pereira")
        self.assertEqual(self.user.currency, "USD")
        self.assertEqual(self.user.timezone, "UTC")

    def test_partial_patch_preserves_omitted_fields(self):
        self.client.force_login(self.user)

        response = self.client.patch(
            self.url,
            {"currency": "EUR"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.currency, "EUR")
        self.assertEqual(self.user.first_name, "João")
        self.assertEqual(self.user.last_name, "Silva")
        self.assertEqual(self.user.timezone, "America/Sao_Paulo")

    def test_patch_ignores_id_modification(self):
        self.client.force_login(self.user)
        original_id = self.user.id

        response = self.client.patch(
            self.url,
            {"id": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.id, original_id)
        self.assertEqual(response.data["id"], str(original_id))

    def test_patch_ignores_email_modification(self):
        self.client.force_login(self.user)

        response = self.client.patch(
            self.url,
            {"email": "new-email@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "user@example.com")
        self.assertEqual(response.data["email"], "user@example.com")

    def test_patch_ignores_is_staff_and_is_superuser_modification(self):
        self.client.force_login(self.user)

        response = self.client.patch(
            self.url,
            {
                "is_staff": True,
                "is_superuser": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_put_method_returns_405(self):
        self.client.force_login(self.user)

        response = self.client.put(
            self.url,
            {
                "first_name": "Carlos",
                "last_name": "Pereira",
                "currency": "USD",
                "timezone": "UTC",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_authenticated_user_only_accesses_own_profile_and_not_other_users(self):
        self.client.force_login(self.user)

        get_response = self.client.get(self.url)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["id"], str(self.user.id))
        self.assertNotEqual(get_response.data["id"], str(self.other_user.id))

        other_user_url = f"/api/v1/users/{self.other_user.id}/"
        other_response = self.client.get(other_user_url)
        self.assertEqual(other_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_with_invalid_currency_returns_400_and_leaves_db_unchanged(self):
        self.client.force_login(self.user)

        response = self.client.patch(
            self.url,
            {"currency": "XYZ"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("currency", response.data)
        self.assertEqual(response.data["currency"][0].code, "invalid_choice")
        self.user.refresh_from_db()
        self.assertEqual(self.user.currency, "BRL")

    def test_patch_with_invalid_timezone_returns_400_and_leaves_db_unchanged(self):
        self.client.force_login(self.user)

        response = self.client.patch(
            self.url,
            {"timezone": "Not/A_Timezone"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("timezone", response.data)
        self.assertEqual(response.data["timezone"][0].code, "invalid_timezone")
        self.user.refresh_from_db()
        self.assertEqual(self.user.timezone, "America/Sao_Paulo")
