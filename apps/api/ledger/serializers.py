from rest_framework import serializers

from .models import Account, AccountType
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
