from rest_framework import serializers

from .models import Account, AccountSystemRole, AccountType, Category, EntrySide, Transaction
from .services import calculate_account_balance


class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()
    is_primary = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ("id", "name", "currency", "account_type", "is_active", "is_primary", "balance")

    def get_balance(self, account):
        return calculate_account_balance(account=account)

    def get_is_primary(self, account):
        return account.system_role == "PRIMARY"


class AccountCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    opening_balance = serializers.DecimalField(max_digits=14, decimal_places=2)

    def validate_name(self, value):
        user = self.context["request"].user
        if user.accounts.filter(name__iexact=value.strip(), is_active=True).exists():
            raise serializers.ValidationError("An active account with this name already exists.")
        return value.strip()

    def create(self, validated_data):
        from .services import record_opening_balance

        user = self.context["request"].user
        account = Account.objects.create(
            user=user, name=validated_data["name"], account_type=AccountType.ASSET, currency=user.currency
        )
        record_opening_balance(account=account, balance=validated_data["opening_balance"])
        return account


class AccountUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ("name",)

    def validate_name(self, value):
        value = value.strip()
        user = self.context["request"].user
        if user.accounts.filter(name__iexact=value, is_active=True).exclude(
            pk=self.instance.pk
        ).exists():
            raise serializers.ValidationError("An active account with this name already exists.")
        return value


class TransactionSerializer(serializers.ModelSerializer):
    amount = serializers.SerializerMethodField()
    kind = serializers.SerializerMethodField()
    category = serializers.CharField(source="category.name", allow_null=True)
    accounts = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = ("id", "description", "currency", "amount", "kind", "category", "accounts", "occurred_at", "status")

    def _entries(self, transaction):
        return list(transaction.entries.all())

    def get_amount(self, transaction):
        entries = self._entries(transaction)
        preferred = next(
            (
                entry for entry in entries
                if entry.account.system_role in {
                    AccountSystemRole.GENERAL_EXPENSE,
                    AccountSystemRole.GENERAL_INCOME,
                }
            ),
            entries[0] if entries else None,
        )
        return preferred.amount if preferred else None

    def get_kind(self, transaction):
        entries = self._entries(transaction)
        if any(entry.account.system_role == AccountSystemRole.GENERAL_EXPENSE for entry in entries):
            return "EXPENSE"
        if any(entry.account.system_role == AccountSystemRole.GENERAL_INCOME for entry in entries):
            return "INCOME"
        return "TRANSFER"

    def get_accounts(self, transaction):
        return [
            {"id": str(entry.account_id), "name": entry.account.name, "side": entry.side}
            for entry in self._entries(transaction)
            if entry.account.account_type == AccountType.ASSET
        ]


class TransactionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ("description", "occurred_at")

    def validate_description(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Description cannot be empty.")
        return value


class CategorySerializer(serializers.ModelSerializer):
    transaction_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = ("id", "name", "is_active", "transaction_count")
        read_only_fields = ("is_active",)

    def validate_name(self, value):
        value = value.strip()
        user = self.context["request"].user
        from .categories import normalize_category_name
        queryset = user.categories.filter(normalized_name=normalize_category_name(value))
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("A category with this name already exists.")
        return value

    def create(self, validated_data):
        return Category.objects.create(user=self.context["request"].user, **validated_data)
