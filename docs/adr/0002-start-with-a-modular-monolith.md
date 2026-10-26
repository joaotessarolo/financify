# ADR 0002: Começar com monólito modular

- Status: aceito
- Data: 2026-10-26

## Contexto

O produto ainda não possui volume, times separados ou requisitos de implantação
independente que justifiquem serviços distribuídos.

## Decisão

Construir um único backend Django separado internamente por contextos de negócio.
O servidor HTTP e os workers podem executar em processos distintos, usando o mesmo
código e banco de dados.

## Consequências

- Transações e desenvolvimento local permanecem simples.
- Limites entre módulos precisarão ser mantidos por convenção e testes.
- Extração para microsserviço só ocorrerá com uma motivação mensurável.

