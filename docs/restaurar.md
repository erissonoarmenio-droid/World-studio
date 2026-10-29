# Restaurar o banco a partir do backup

O servidor guarda uma cópia completa do banco por dia no Cloudflare R2, bucket
`world-studio-backup`, pasta `banco/` (`AAAA-MM-DD.dump`), pelos últimos 14 dias.
Cada backup gera o evento `backup_feito` (ou `backup_falhou`), e o `/saude` mostra
`"backup": "ok"` ou `"atrasado"` (mais de 30 h sem backup).

## Fazer um backup agora
No Shell do Render: `python -m app.nucleo.backup --agora`
(se o de hoje já existe, responde `ja_existia`).

## Restaurar (só com o Eri decidindo)
Restaurar **substitui** os dados. Primeiro num banco novo, para conferir; só depois no de produção.

1. Baixar o arquivo do dia no painel da Cloudflare (R2 → `world-studio-backup` → `banco/`).
2. Criar um banco Postgres 16 vazio (no Render: New → PostgreSQL) e copiar a
   "External Database URL" dele.
3. No computador com o Postgres 16 instalado:
   ```
   pg_restore --no-owner --no-privileges --dbname "<URL do banco novo>" AAAA-MM-DD.dump
   ```
4. Conferir as tabelas (`lojas`, `pessoas`, `eventos`, `trabalhos`, `midias`).
5. Para voltar a produção para esse ponto: apontar o `DATABASE_URL` do serviço para o
   banco restaurado (ou restaurar no banco de produção com `--clean`), sempre com o
   servidor pausado e depois de um backup novo do estado atual.
