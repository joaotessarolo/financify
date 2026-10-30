import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase


class UserManagerTests(TestCase):
    """
    Tests for the custom user manager:
        - Create normal user with email and password.
        - Password hashing.
        - Default values.
        - Email normalization.
        - Error without email.
        - Create superuser.
        - Rejection of superuser with is_staff=False.
        - Rejection of superuser with is_superuser=False.
        - Database rejects duplicate email regardless of letter case.
    """

    def setUp(self):
        self.user_model = get_user_model()
        self.email = "user@example.com"
        self.password = "strong-password-123"

    def test_create_user_with_email_and_password(self):
        """Test user creation with email and password."""
        user = self.user_model.objects.create_user(
            email=self.email,
            password=self.password,
        )

        self.assertEqual(user.email, self.email)
        self.assertTrue(user.check_password(self.password))
        self.assertTrue(user.is_active)
        self.assertEqual(str(user), self.email)
        field_names = [field.name for field in user._meta.fields]
        self.assertNotIn("username", field_names)

    def test_create_user_password_is_hashed(self):
        """Test user password is hashed."""
        user = self.user_model.objects.create_user(
            email=self.email,
            password=self.password,
        )

        self.assertNotEqual(user.password, self.password)
        self.assertTrue(user.check_password(self.password))

    def test_create_user_default_values(self):
        """Test user default values."""
        user = self.user_model.objects.create_user(
            email=self.email,
            password=self.password,
        )

        self.assertIsInstance(user.id, uuid.UUID)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertEqual(user.currency, "BRL")
        self.assertEqual(user.timezone, "America/Sao_Paulo")

    def test_create_user_email_normalization(self):
        """Test user email normalization."""
        user = self.user_model.objects.create_user(
            email="USER@EXAMPLE.COM",
            password=self.password,
        )

        self.assertEqual(user.email, "user@example.com")

    def test_create_user_without_email_raises_error(self):
        """Test user creation without email raises error."""
        for invalid_email in ("", None):
            with self.subTest(email=invalid_email):
                with self.assertRaisesMessage(
                    ValueError,
                    "The email address is required.",
                ):
                    self.user_model.objects.create_user(
                        email=invalid_email,
                        password=self.password,
                    )

    def test_create_superuser(self):
        """Test superuser creation with email and password."""
        admin = self.user_model.objects.create_superuser(
            email="admin@example.com",
            password="admin-password-123",
        )

        self.assertEqual(admin.email, "admin@example.com")
        self.assertTrue(admin.check_password("admin-password-123"))
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_active)
        self.assertEqual(str(admin), "admin@example.com")

    def test_create_superuser_with_is_staff_false_raises_error(self):
        """Test superuser creation with is_staff=False raises error."""
        with self.assertRaisesMessage(
            ValueError,
            "Superuser must have is_staff=True.",
        ):
            self.user_model.objects.create_superuser(
                email="admin@example.com",
                password="admin-password-123",
                is_staff=False,
            )

    def test_create_superuser_with_is_superuser_false_raises_error(self):
        """Test superuser creation with is_superuser=False raises error."""
        with self.assertRaisesMessage(
            ValueError,
            "Superuser must have is_superuser=True.",
        ):
            self.user_model.objects.create_superuser(
                email="admin@example.com",
                password="admin-password-123",
                is_superuser=False,
            )

    def test_database_rejects_duplicate_email_case_insensitive(self):
        """Test database constraint rejects duplicate email with different casing."""
        self.user_model.objects.create_user(
            email="user@example.com",
            password=self.password,
        )

        with self.assertRaises(IntegrityError):
            self.user_model.objects.create(
                email="USER@EXAMPLE.COM",
                password=self.password,
            )
