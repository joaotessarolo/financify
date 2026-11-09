from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ledger.services import ensure_default_accounts


class DashboardSummaryTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="dashboard@example.com",
            password="StrongPassword!123",
        )
        ensure_default_accounts(user=cls.user)
        cls.url = reverse("ledger:dashboard-summary")

    def test_requires_authentication(self):
        self.assertEqual(
            self.client.get(self.url).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_returns_real_user_summary(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["currency"], "BRL")
        self.assertEqual(len(response.data["accounts"]), 1)
        self.assertEqual(response.data["month"]["net"], 0)
