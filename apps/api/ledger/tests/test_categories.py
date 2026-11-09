from django.contrib.auth import get_user_model
from django.test import TestCase

from ..categories import (
    classify_category,
    create_category,
    ensure_default_categories,
    find_category,
)


class CategoryServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="categories@example.com",
            password="StrongPassword!123",
        )

    def test_creates_defaults_idempotently(self):
        first = ensure_default_categories(user=self.user)
        second = ensure_default_categories(user=self.user)

        self.assertEqual(len(first), len(second))
        self.assertIsNotNone(find_category(user=self.user, name="alimentacao"))

    def test_classifies_known_description_and_falls_back(self):
        self.assertEqual(
            classify_category(user=self.user, description="compras no mercado").name,
            "Mercado",
        )
        self.assertEqual(
            classify_category(user=self.user, description="coisa diferente").name,
            "Outros",
        )

    def test_creates_custom_category_without_duplicates(self):
        category = create_category(user=self.user, name="Pets")
        self.assertEqual(category.name, "Pets")
        with self.assertRaises(ValueError):
            create_category(user=self.user, name="pets")
