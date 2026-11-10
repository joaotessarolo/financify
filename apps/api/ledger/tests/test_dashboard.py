from decimal import Decimal

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

    def test_lists_authenticated_users_asset_accounts(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("ledger:account-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertTrue(response.data[0]["is_primary"])
        self.assertEqual(response.data[0]["balance"], Decimal("0.00"))

    def test_creates_renames_and_archives_additional_account(self):
        self.client.force_login(self.user)
        created = self.client.post(
            reverse("ledger:account-list"),
            {"name": "Inter", "opening_balance": "500.00"},
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        account_url = reverse("ledger:account-detail", args=[created.data["id"]])

        renamed = self.client.patch(account_url, {"name": "Inter PJ"})
        self.assertEqual(renamed.status_code, status.HTTP_200_OK)
        self.assertEqual(renamed.data["name"], "Inter PJ")

        archived = self.client.delete(account_url)
        self.assertEqual(archived.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.get(reverse("ledger:account-list")).data[0]["name"], "Conta principal")

    def test_refuses_to_archive_primary_account(self):
        self.client.force_login(self.user)
        primary = self.user.accounts.get(system_role="PRIMARY")
        response = self.client.delete(reverse("ledger:account-detail", args=[primary.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_lists_posted_transactions_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("ledger:transaction-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_transaction_filters_accept_supported_query_parameters(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("ledger:transaction-list"),
            {"q": "market", "kind": "EXPENSE", "from": "2026-01-01", "to": "2026-12-31"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_transaction_detail_is_scoped_to_authenticated_user(self):
        import uuid

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("ledger:transaction-detail", args=[uuid.uuid4()])
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_manages_categories_for_authenticated_user(self):
        self.client.force_login(self.user)
        created = self.client.post(reverse("ledger:category-list"), {"name": "Pets"})
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        url = reverse("ledger:category-detail", args=[created.data["id"]])
        self.assertEqual(self.client.patch(url, {"name": "Animais"}).data["name"], "Animais")
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_204_NO_CONTENT)

    def test_sets_and_removes_monthly_budget(self):
        from ledger.categories import ensure_default_categories

        category = ensure_default_categories(user=self.user)[0]
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("ledger:budget-list"),
            {"category_id": category.id, "monthly_limit": "500.00"},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["monthly_limit"], "500.00")
        self.assertEqual(
            self.client.delete(
                reverse("ledger:budget-detail", args=[response.data["id"]])
            ).status_code,
            status.HTTP_204_NO_CONTENT,
        )
