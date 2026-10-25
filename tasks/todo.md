# Tarefas — módulo nucleo (detalhes em tasks/plan.md)

## Fase 1 — Fundação
- [x] 1. Esqueleto do projeto (25/10): `/saude`, config por ambiente, Dockerfile com usuário sem privilégios, ruff, pytest (3 testes, cobertura 100%), imagem testada (331 MB)
- [x] 2. Banco de dados e migrações (25/10): conexão Postgres com reconexão automática, Alembic com URL só do ambiente, migração 0001, banco de teste PostgreSQL 16 real e descartável, `/saude` com banco (503 se fora), 9 testes, cobertura 100%
- [ ] 3. Publicar no Railway (Eri cria GitHub e Railway)
- [ ] Parada A

## Fase 2 — Cadastro
- [ ] 4. Lojas, pessoas e eventos
- [ ] 5. Convite da funcionária
- [ ] 6. Consentimentos com versão
- [ ] 7. Perfil da loja e dados fiscais
- [ ] Parada B

## Fase 3 — Palavra-senha
- [ ] 8. Palavra-senha da dona

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
