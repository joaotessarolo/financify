import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

from ..serializers import UserRegistrationSerializer


class UserRegistrationSerializerTests(TestCase):
    """
    Tests for UserRegistrationSerializer:
        - Valid payload and user creation.
        - Password hashed in database.
        - Password and password_confirmation absent from serialized output.
        - Password mismatch error.
        - Weak password rejection.
        - Invalid email format rejection.
        - Case-insensitive duplicate email rejection.
        - Administrative fields ignored.
        - Default currency and timezone values.
        - Custom profile fields saved on registration.
    """

    def setUp(self):
        self.user_model = get_user_model()
        self.valid_payload = {
            "email": "User@Example.com",
            "password": "StrongPassword!123",
            "password_confirmation": "StrongPassword!123",
        }

    def test_valid_payload_creates_user_with_hashed_password(self):
        """Test valid payload is valid, creates user, and hashes password."""
        serializer = UserRegistrationSerializer(data=self.valid_payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()

        self.assertEqual(self.user_model.objects.count(), 1)
        self.assertIsInstance(user.id, uuid.UUID)
        self.assertEqual(user.email, "user@example.com")
        self.assertNotEqual(user.password, self.valid_payload["password"])
        self.assertTrue(user.check_password(self.valid_payload["password"]))

    def test_passwords_are_not_in_serialized_output(self):
        """Test password and password_confirmation are omitted from serializer.data."""
        serializer = UserRegistrationSerializer(data=self.valid_payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()

        self.assertNotIn("password", serializer.data)
        self.assertNotIn("password_confirmation", serializer.data)
        self.assertIn("id", serializer.data)
        self.assertEqual(serializer.data["email"], "user@example.com")

    def test_mismatched_passwords_are_rejected(self):
        """Test registration fails when password and password_confirmation differ."""
        payload = {
            **self.valid_payload,
            "password_confirmation": "DifferentPassword!123",
        }
        serializer = UserRegistrationSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("password_confirmation", serializer.errors)

    def test_weak_password_is_rejected(self):
        """Test registration fails when password is too weak."""
        payload = {
            **self.valid_payload,
            "password": "123",
            "password_confirmation": "123",
        }
        serializer = UserRegistrationSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("password", serializer.errors)

    def test_invalid_email_is_rejected(self):
        """Test registration fails with an invalid email address."""
        payload = {
            **self.valid_payload,
            "email": "not-an-email",
        }
        serializer = UserRegistrationSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)
        self.assertEqual(serializer.errors["email"][0].code, "invalid")

    def test_duplicate_email_case_insensitive_is_rejected(self):
        """Test duplicate email with different casing is rejected."""
        self.user_model.objects.create_user(
            email="user@example.com",
            password="StrongPassword!123",
        )
        payload = {
            **self.valid_payload,
            "email": "USER@EXAMPLE.COM",
        }
        serializer = UserRegistrationSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)
        self.assertEqual(serializer.errors["email"][0].code, "unique")

    def test_administrative_fields_are_ignored(self):
        """Test is_staff, is_superuser, and custom id cannot be set via payload."""
        custom_id = uuid.uuid4()
        payload = {
            **self.valid_payload,
            "id": str(custom_id),
            "is_staff": True,
            "is_superuser": True,
            "is_active": False,
        }
        serializer = UserRegistrationSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()

        self.assertNotEqual(user.id, custom_id)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_default_currency_and_timezone_values(self):
        """Test default currency and timezone are applied when omitted."""
        serializer = UserRegistrationSerializer(data=self.valid_payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()

        self.assertEqual(user.currency, "BRL")
        self.assertEqual(user.timezone, "America/Sao_Paulo")
        self.assertEqual(serializer.data["currency"], "BRL")
        self.assertEqual(serializer.data["timezone"], "America/Sao_Paulo")

    def test_profile_fields_are_saved_when_provided(self):
        """Test first_name, last_name, currency, and timezone are saved when sent."""
        payload = {
            **self.valid_payload,
            "first_name": "João",
            "last_name": "Silva",
            "currency": "USD",
            "timezone": "UTC",
        }
        serializer = UserRegistrationSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()

        self.assertEqual(user.first_name, "João")
        self.assertEqual(user.last_name, "Silva")
        self.assertEqual(user.currency, "USD")
        self.assertEqual(user.timezone, "UTC")
        self.assertEqual(serializer.data["first_name"], "João")
        self.assertEqual(serializer.data["last_name"], "Silva")
        self.assertEqual(serializer.data["currency"], "USD")
        self.assertEqual(serializer.data["timezone"], "UTC")
