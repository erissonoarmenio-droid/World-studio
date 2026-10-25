# Plano de construção: módulo `nucleo`

Versão 0.1 — 25/out/2026. Método: skill `planning-and-task-breakdown`. Base: `aios/projects/spec-nucleo.md` v1.0 (aprovada). **Aguardando aprovação de Eri** antes de qualquer código. Quando o repositório `world-estudio` existir, este plano vira `tasks/plan.md` e a lista vira `tasks/todo.md` lá dentro.

## Visão geral
Construir a base do sistema em 14 tarefas pequenas, cada uma deixando o sistema funcionando e testado. Ordem: esqueleto → banco → **servidor no ar cedo** (para descobrir problemas de hospedagem logo) → cadastro → palavra-senha → fila → mídias, LGPD e backup → fechamento de segurança. Paradas para revisão com o Eri depois de cada fase.

## Decisões de arquitetura
- **Servidor no ar na 3ª tarefa**, não no fim: o Render é o maior risco externo (incidentes de 2026), então testamos a publicação cedo, com quase nada dentro.
- **Fatias verticais:** cada tarefa entrega tabela + funções + testes + evento de auditoria juntos (não "todas as tabelas primeiro").
- **Postgres de verdade nos testes:** o ambiente de trabalho já tem o PostgreSQL 16 (o mesmo usado no Render), então os testes rodam contra um banco real local, sem simulação.
- **Fila no próprio Postgres** (`FOR UPDATE SKIP LOCKED`), sem Redis, como na especificação.
- **R2 simulado nos testes** (biblioteca de simulação de S3) e real só no ambiente publicado.
- **Eu escrevo e testo aqui; você cria as contas e aprova.** Contas necessárias, cada uma só na tarefa em que vira necessária: GitHub (tarefa 3), Render (tarefa 3), Cloudflare R2 (tarefa 11).

## Tarefas

### Fase 1 — Fundação
**Tarefa 1: Esqueleto do projeto**
- O que faz: projeto Python com uv, FastAPI respondendo `/saude` (só "processo ok" por enquanto), leitura das variáveis de ambiente, Dockerfile, ruff e pytest configurados, `.env.example` só com nomes.
- Pronto quando: `uv run pytest` passa; `uv run ruff check .` limpo; a imagem Docker sobe e `/saude` responde 200.
- Verificar: testes + build da imagem + chamada local ao `/saude`.
- Depende de: nada. Arquivos: `pyproject.toml`, `app/main.py`, `app/config.py`, `Dockerfile`, `tests/test_saude.py`. Tamanho: P.

**Tarefa 2: Banco de dados e migrações**
- O que faz: conexão com o Postgres, Alembic configurado, primeira migração (vazia de domínio), banco de teste automático nos testes, `/saude` passa a checar o banco.
- Pronto quando: `alembic upgrade head` roda num banco vazio; `/saude` diz "banco ok" ou "banco fora" corretamente; testes usam um banco limpo a cada execução.
- Verificar: testes + migração num banco novo.
- Depende de: 1. Arquivos: `app/nucleo/db.py`, `migrations/`, `alembic.ini`, `tests/conftest.py`. Tamanho: M.

**Tarefa 3: Publicar no Render (você participa)**
- O que faz: você cria o repositório privado `world-estudio` no GitHub e a conta no Render (região Leste dos EUA); eu subo o código; o Render publica o serviço `web` com o Postgres.
- Pronto quando: o endereço público responde `/saude` com "banco ok"; uma mudança no código publicada sozinha aparece no ar.
- Verificar: chamada ao `/saude` publicado.
- Depende de: 2. Arquivos: `render.yaml`, `README.md`. Tamanho: P.

**Parada A (com você):** testes passando, servidor no ar, você vê o `/saude` respondendo.

### Fase 2 — Cadastro da loja
**Tarefa 4: Lojas, pessoas e registro de eventos**
- O que faz: tabelas de loja, pessoa (com a dona) e eventos; funções de criar, ler e editar; todo cadastro e edição vira evento ("quem fez o quê, quando").
- Pronto quando: criar loja + dona registra 2 eventos; id do Telegram é único; dados inválidos são recusados com motivo.
- Verificar: testes de unidade e de banco.
- Depende de: 2. Arquivos: `app/nucleo/modelos/`, `lojas.py`, `pessoas.py`, `eventos.py`, testes. Tamanho: M.

**Tarefa 5: Convite da funcionária**
- O que faz: a dona gera um código de convite (uso único, 48 h, guardado embaralhado); a funcionária entra com ele; `pode_aprovar_gastos` só muda por ação da dona.
- Pronto quando: convite usado uma vez funciona e na segunda é recusado; convite vencido é recusado; funcionária não consegue se dar permissão.
- Verificar: testes, inclusive de abuso. Depende de: 4. Arquivos: `pessoas.py`, modelo de convite, testes. Tamanho: P.

**Tarefa 6: Consentimentos com versão**
- O que faz: registrar e revogar aceites (termos e privacidade, dados agregados, Instagram, WhatsApp, ordem fixa, modo automático, clone) com versão do texto e horário; função que exige o aceite dos termos.
- Pronto quando: revogar guarda o histórico (não apaga); sem aceite de termos, `exigir_termos_aceitos` recusa.
- Verificar: testes. Depende de: 4. Arquivos: `consentimentos.py`, modelo, testes. Tamanho: P.

**Tarefa 7: Perfil da loja e dados fiscais**
- O que faz: o perfil flexível (a "lista invisível" da influencer) com origem e data de cada campo; a tabela fiscal vazia no piloto, com conferência do dígito do CNPJ/CPF pronta.
- Pronto quando: atualizar um campo guarda de onde veio e quando; CNPJ inválido é recusado; tudo vira evento.
- Verificar: testes. Depende de: 4. Arquivos: `lojas.py`, modelos, testes. Tamanho: P.

**Parada B (com você):** revisão do cadastro: o que é guardado bate com o que combinamos?

### Fase 3 — Palavra-senha
**Tarefa 8: Palavra-senha da dona**
- O que faz: criar (só a dona, com dica opcional), conferir, janela de 30 min, bloqueio de 15 min depois de 5 erros, troca liberada pelo Eri; tudo vira evento; função para o bot apagar a mensagem da senha.
- Pronto quando: a palavra só existe embaralhada (Argon2id); 5 erros bloqueiam; funcionária não consegue criar; a troca pelo Eri funciona e fica registrada.
- Verificar: testes, com força bruta simulada. Depende de: 4, 6. Arquivos: `senha.py`, modelos, testes. Tamanho: M.

### Fase 4 — Fila de trabalhos
**Tarefa 9: Enfileirar sem gastar duas vezes**
- O que faz: tabela de trabalhos; `enfileirar` com `chave_unica`; recusa sem aceite de termos; evento a cada trabalho.
- Pronto quando: pedir duas vezes a mesma coisa devolve o mesmo trabalho; loja sem termos é recusada.
- Verificar: testes. Depende de: 6. Arquivos: `fila/`, modelo, testes. Tamanho: P.

**Tarefa 10: O trabalhador**
- O que faz: o processo que pega trabalhos, conclui, falha com nova tentativa (espera crescente, máx. 3) e devolve travados; `/saude` passa a checar a fila; serviço `trabalhador` no Render.
- Pronto quando: teste com 2 trabalhadores ao mesmo tempo sem pegar o mesmo trabalho; falha re-tentada até 3 vezes e depois vira "falhou" + evento; travado há 15 min volta.
- Verificar: testes de concorrência + o trabalhador rodando no Render. Depende de: 9, 3. Arquivos: `fila/trabalhador.py`, `main.py`, testes. Tamanho: M.

**Parada C (com você):** fila funcionando no ar com um trabalho de teste.

### Fase 5 — Mídias, LGPD e backup
**Tarefa 11: Armazenamento de fotos e vídeos (você participa)**
- O que faz: você cria a conta Cloudflare e o bucket privado; eu ligo enviar, ler (link de 1 h) e apagar, uma pasta por loja; `/saude` checa o R2.
- Pronto quando: uma loja não consegue ler mídia de outra; o link expira; `/saude` mostra "R2 ok".
- Verificar: testes com R2 simulado + um envio real no ar. Depende de: 4, 3. Arquivos: `midia.py`, modelo, testes. Tamanho: M.

**Tarefa 12: Exportar e apagar uma loja (LGPD)**
- O que faz: exportar todos os dados da loja num arquivo; apagar banco + mídias deixando só um evento anônimo; loja cancelada é apagada sozinha depois de 60 dias.
- Pronto quando: depois de apagar, nada da loja sobra no banco nem no R2; a exportação traz tudo o que foi guardado.
- Verificar: testes de ponta a ponta. Depende de: 7, 8, 11. Arquivos: `lojas.py`, tarefa de limpeza, testes. Tamanho: M.

**Tarefa 13: Backup diário**
- O que faz: cópia completa do banco todo dia às 3h para um bucket separado no R2; guarda 14 dias; roteiro de restauração.
- Pronto quando: o arquivo do dia aparece no R2; restaurar num banco vazio recupera tudo.
- Verificar: backup e restauração reais, uma vez com você. Depende de: 11. Arquivos: `backup.py`, configuração da tarefa agendada, `docs/restaurar.md`. Tamanho: M.

**Tarefa 14: Fechamento de segurança**
- O que faz: varredura de segredos no repositório, cobertura ≥ 80% no núcleo, checklist da skill `security-and-hardening` (entradas validadas, nada sensível em log, erros sem detalhe interno).
- Pronto quando: os 9 critérios de pronto da especificação estão todos marcados.
- Verificar: relatório da varredura + cobertura + lista dos 9 critérios. Depende de: todas. Tamanho: P.

**Parada final (com você):** conferimos os 9 critérios juntos e o núcleo é dado como pronto. Próximo módulo: `creditos`.

## Riscos e como travamos
| Risco | Impacto | Trava |
|---|---|---|
| Render fora do ar ou derrubando serviço (já aconteceu em 2026) | Alto | Publicação testada cedo (tarefa 3); Docker para mudar de hospedagem; backup diário fora dele (tarefa 13) |
| Atraso nas contas (GitHub, Render, Cloudflare) | Médio | Tudo é construído e testado aqui antes; cada conta só é pedida na tarefa que precisa |
| Versão do `pg_dump` diferente da do banco no Render | Médio | Usar a mesma versão do Postgres nos dois; testar restauração de verdade |
| Erro na fila gastando duas vezes | Alto | `chave_unica` + teste de concorrência antes de qualquer geração real |
| Vazamento de dados de uma loja para outra | Alto | Pasta por loja, checagem de dono em toda leitura, teste de abuso específico |

## Perguntas em aberto
Nenhuma. As contas serão pedidas nas tarefas 3 e 11.
