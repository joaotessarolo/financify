ACCOUNT_ONBOARDING_PROMPT = (
    "Tudo conectado. Agora vamos preparar sua conta principal.\n\n"
    "Me diga o nome da conta e, se quiser, o saldo de hoje.\n"
    "Exemplos: “Nubank, 2.500 reais” ou apenas “Itaú”."
)


def balance_prompt(account_name: str) -> str:
    return (
        f"Certo, vou usar “{account_name}” como sua conta principal.\n\n"
        "Qual é o saldo dela hoje? Você pode responder “50 mil”, "
        "“1.250,90”, “0” ou até “-300”."
    )


def onboarding_complete(account_name: str, currency: str, balance) -> str:
    formatted = f"{balance:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return (
        "Conta pronta!\n\n"
        f"{account_name} · {currency} {formatted}\n\n"
        "Quando quiser registrar algo, mande uma frase como "
        "“gastei 40 no mercado”."
    )


INVALID_ACCOUNT_SETUP = (
    "Não consegui identificar a conta. Tente algo como “Nubank, 2.500 reais” "
    "ou envie somente o nome da conta."
)

INVALID_BALANCE = (
    "Não consegui entender esse saldo. Tente “50 mil”, “1.250,90”, “0” "
    "ou “-300”."
)
