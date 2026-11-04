from django.contrib import admin

from .models import TelegramIdentity, TelegramLinkToken, TelegramUpdate


@admin.register(TelegramIdentity)
class TelegramIdentityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "telegram_user_id",
        "private_chat_id",
        "linked_at",
        "revoked_at",
    )
    list_filter = ("revoked_at",)
    search_fields = (
        "user__email",
        "telegram_user_id",
        "private_chat_id",
    )
    readonly_fields = (
        "id",
        "linked_at",
        "updated_at",
    )


@admin.register(TelegramLinkToken)
class TelegramLinkTokenAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "expires_at",
        "used_at",
        "created_at",
    )
    list_filter = ("used_at",)
    search_fields = ("user__email",)
    readonly_fields = (
        "id",
        "token_digest",
        "created_at",
    )


@admin.register(TelegramUpdate)
class TelegramUpdateAdmin(admin.ModelAdmin):
    list_display = (
        "update_id",
        "update_type",
        "status",
        "error_code",
        "received_at",
        "processed_at",
    )
    list_filter = (
        "update_type",
        "status",
    )
    search_fields = (
        "update_id",
        "error_code",
    )
    readonly_fields = (
        "id",
        "received_at",
    )
