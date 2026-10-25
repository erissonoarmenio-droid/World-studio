# Tarefas — módulo nucleo (detalhes em tasks/plan.md)

## Fase 1 — Fundação
- [x] 1. Esqueleto do projeto (25/10): `/saude`, config por ambiente, Dockerfile com usuário sem privilégios, ruff, pytest (3 testes, cobertura 100%), imagem testada (331 MB)
- [x] 2. Banco de dados e migrações (25/10): conexão Postgres com reconexão automática, Alembic com URL só do ambiente, migração 0001, banco de teste PostgreSQL 16 real e descartável, `/saude` com banco (503 se fora), 9 testes, cobertura 100%
- [x] 3. Publicar no Render (25/10: no ar em https://world-studio-web.onrender.com — `/saude` com processo e banco ok; docs fechadas em produção)
- [ ] Parada A

## Fase 2 — Cadastro
- [x] 4. Lojas, pessoas e registro de eventos (25/10: 36 testes, cobertura 99%; eventos travados contra edição no próprio banco)
- [x] 5. Convite da funcionária (25/10: código de 8 caracteres, só hash no banco, uso único, 48 h; permissão de gastos só pela dona)
- [x] 6. Consentimentos com versão (25/10: versão nova substitui a anterior, revogar guarda histórico, aceites da loja só pela dona, exigir_termos_aceitos)
- [x] 7. Perfil da loja e dados fiscais (25/10: cada campo com origem e data; CPF/CNPJ conferidos pelo dígito; número nunca vai para evento)
- [ ] Parada B

## Fase 3 — Palavra-senha
- [x] 8. Palavra-senha da dona (25/10: Argon2id, janela de 30 min, 5 erros = 15 min de bloqueio, troca liberada pelo Eri por 24 h, força bruta simulada)

## Fase 4 — Fila
- [ ] 9. Enfileirar sem gastar duas vezes
- [ ] 10. O trabalhador
- [ ] Parada C

## Fase 5 — Mídias, LGPD e backup
- [ ] 11. Armazenamento (Eri cria Cloudflare R2)
- [ ] 12. Exportar e apagar loja
- [ ] 13. Backup diário
- [ ] 14. Fechamento de segurança
- [ ] Parada final
