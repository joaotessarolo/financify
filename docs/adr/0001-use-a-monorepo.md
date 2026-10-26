# ADR 0001: Usar monorepo

- Status: aceito
- Data: 2026-10-26

## Contexto

Backend, web e futuro mobile pertencem ao mesmo produto, serão mantidos inicialmente
por uma pessoa e evoluirão de forma coordenada.

## Decisão

Manter aplicações e pacotes no mesmo repositório. Cada ecossistema preservará seu
próprio gerenciamento de dependências e seus limites.

## Consequências

- Mudanças de API e consumidores podem ser revisadas juntas.
- A integração contínua deve executar apenas os trabalhos afetados quando isso se
  tornar relevante.
- Compartilhar repositório não autoriza acoplamento direto entre os domínios.
- Um componente poderá ser extraído quando tiver ciclo e operação independentes.

