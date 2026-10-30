import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


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
