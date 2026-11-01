from django.db import models


class Currency(models.TextChoices):
    BRL = "BRL", "Brazilian Real"
    USD = "USD", "US Dollar"
    EUR = "EUR", "Euro"
