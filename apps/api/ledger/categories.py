import unicodedata

from django.db import IntegrityError, transaction as db_transaction

from .models import Category


DEFAULT_CATEGORY_KEYWORDS = {
    "Mercado": ("mercado", "supermercado", "feira"),
    "Alimentação": ("almoço", "almoco", "jantar", "lanche", "restaurante", "café"),
    "Transporte": ("uber", "99", "ônibus", "onibus", "gasolina", "combustível"),
    "Moradia": ("aluguel", "condomínio", "condominio", "energia", "internet"),
    "Saúde": ("farmácia", "farmacia", "médico", "medico", "consulta"),
    "Lazer": ("cinema", "show", "jogo", "viagem"),
    "Salário": ("salário", "salario", "pagamento"),
    "Outros": (),
}


def normalize_category_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().casefold())
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    )


def ensure_default_categories(*, user) -> list[Category]:
    categories = []
    for name in DEFAULT_CATEGORY_KEYWORDS:
        category, _ = Category.objects.get_or_create(
            user=user,
            normalized_name=normalize_category_name(name),
            defaults={"name": name},
        )
        categories.append(category)
    return categories


def find_category(*, user, name: str) -> Category | None:
    return user.categories.filter(
        normalized_name=normalize_category_name(name), is_active=True
    ).first()


def classify_category(*, user, description: str) -> Category:
    ensure_default_categories(user=user)
    normalized = normalize_category_name(description)
    for name, keywords in DEFAULT_CATEGORY_KEYWORDS.items():
        if keywords and any(
            normalize_category_name(keyword) in normalized for keyword in keywords
        ):
            return find_category(user=user, name=name)
    return find_category(user=user, name="Outros")


@db_transaction.atomic
def create_category(*, user, name: str) -> Category:
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("Invalid category name.")
    try:
        return Category.objects.create(user=user, name=name)
    except IntegrityError as exc:
        raise ValueError("Category already exists.") from exc
