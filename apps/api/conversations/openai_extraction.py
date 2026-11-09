from typing import Literal

from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from .ai_extraction import (
    StructuredTransactionCandidate,
    TransactionExtractionProviderError,
)


class OpenAITransactionCandidate(BaseModel):
    supported: bool
    kind: Literal["EXPENSE", "INCOME", "TRANSFER"] | None
    amount: str | None
    description: str | None
    account_name: str | None
    category_name: str | None
    source_account_name: str | None
    destination_account_name: str | None


class OpenAIStructuredTransactionProvider:
    def __init__(self, *, api_key: str, model: str, timeout: float, client=None):
        self.model = model
        self.client = client or OpenAI(api_key=api_key, timeout=timeout)

    def extract(self, text: str) -> StructuredTransactionCandidate:
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=(
                    "Extraia apenas uma despesa ou receita pessoal da mensagem em "
                    "português. Use EXPENSE para dinheiro gasto e INCOME para dinheiro "
                    "recebido. Retorne amount como decimal positivo com ponto, sem símbolo "
                    "de moeda. Crie uma descrição curta e fiel. Se a mensagem não registrar "
                    "uma transação, marque supported=false e deixe os outros campos nulos. "
                    "Quando houver uma conta explicitamente citada, copie seu nome para "
                    "account_name; caso contrário, retorne null."
                    " Sugira em category_name uma categoria curta para o lançamento."
                    " Para transferência, use TRANSFER e informe source_account_name e "
                    "destination_account_name; não trate a movimentação como gasto."
                ),
                input=text,
                text_format=OpenAITransactionCandidate,
                store=False,
            )
        except OpenAIError as exc:
            raise TransactionExtractionProviderError(
                "OpenAI could not extract the transaction."
            ) from exc

        parsed = response.output_parsed
        if parsed is None:
            raise TransactionExtractionProviderError(
                "OpenAI returned no structured transaction."
            )
        return StructuredTransactionCandidate(
            supported=parsed.supported,
            kind=parsed.kind,
            amount=parsed.amount,
            description=parsed.description,
            account_name=parsed.account_name,
            category_name=parsed.category_name,
            source_account_name=parsed.source_account_name,
            destination_account_name=parsed.destination_account_name,
        )
