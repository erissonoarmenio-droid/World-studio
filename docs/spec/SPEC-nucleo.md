# Spec: `nucleo` — a base do sistema do estúdio W-orld

Versão 1.0 — 25/out/2026. Método: skill `spec-driven-development` (fase 1). **Aprovada por Eri em 25/10, 12h14**, com as respostas: recuperação da palavra-senha passa pelo Eri no piloto (sem provedor de e-mail por enquanto); região Leste dos EUA; repositório `world-estudio`.
Mapa aprovado: `aios/projects/sistema-mapa-capacidades.md` (v1.0). Este é o 1º módulo da ordem de construção.

## Objetivo
Construir a base onde todos os outros módulos rodam: o servidor no ar 24 h, o banco de dados com o **cadastro das lojas**, a **fila de trabalhos** (para gerações demoradas), o **registro de tudo o que acontece e do que custa**, o **armazenamento das fotos e vídeos** e o **backup diário**. Sem tela nem conversa ainda: isso vem nos módulos `conversa` e `central`.

**Quem usa:** os outros módulos (por funções internas) e o Eri (pela Central, depois).

**Histórias:**
- Como Eri, quero que o servidor fique no ar sozinho e me diga se está saudável.
- Como Eri, quero o cadastro de cada loja (pessoas, loja, dados fiscais quando houver, marca, influencer, consentimentos) guardado num lugar só, para ver e editar na Central.
- Como dona da loja, quero que só eu consiga comprar créditos, mudar o plano e ligar o modo automático, com a minha palavra-senha, e recuperá-la se esquecer.
- Como Eri, quero que uma geração demorada (vídeo de 3–5 min) não trave a conversa e que, se falhar, seja tentada de novo sem duplicar gasto.
- Como Eri, quero saber quem fez o quê, quando e quanto custou.
- Como Eri, quero um backup diário fora do Render e poder apagar ou exportar os dados de uma loja (LGPD).

## Tech stack
- **Python 3.12**, **FastAPI** (servidor), **Uvicorn**.
- **PostgreSQL** (Render) com **SQLAlchemy 2** e migrações **Alembic**; driver **psycopg 3**.
- **Pydantic v2** para validar tudo que entra.
- **Cloudflare R2** (compatível com S3, via **boto3**) para mídias e backups.
- **argon2-cffi** (Argon2id) para palavra-senha e códigos de recuperação.
- Gerenciador de pacotes **uv**, com versões travadas no `uv.lock`; **Docker** para rodar igual no Render e em qualquer lugar (portabilidade, decisão de 25/10).
- Testes **pytest**; estilo **ruff**.
- Recuperação da palavra-senha **pelo Eri** no piloto (decisão de 25/10); envio de código por e-mail fica para quando houver domínio próprio.

## Comandos
```
Instalar:        uv sync
Rodar local:     uv run uvicorn app.main:app --reload
Trabalhador:     uv run python -m app.nucleo.fila.trabalhador
Migrações:       uv run alembic upgrade head
Nova migração:   uv run alembic revision --autogenerate -m "descricao"
Testes:          uv run pytest -q
Cobertura:       uv run pytest --cov=app/nucleo --cov-report=term-missing
Estilo:          uv run ruff check --fix . && uv run ruff format .
Imagem Docker:   docker build -t world-estudio .
Backup manual:   uv run python -m app.nucleo.backup --agora
```
No Render: 2 serviços a partir da mesma imagem (`web` = Uvicorn; `trabalhador` = fila) + Postgres + tarefa agendada diária do backup.

## Estrutura do projeto
```
app/
  main.py                 → cria o FastAPI e registra as rotas dos módulos
  config.py               → lê as variáveis de ambiente (segredos nunca no código)
  nucleo/
    db.py                 → conexão e sessão do banco
    modelos/              → tabelas (lojas, pessoas, perfil, fiscal, consentimentos, senha, convites, trabalhos, eventos, mídias)
    lojas.py              → criar/ler/editar loja e perfil; exportar e apagar (LGPD)
    pessoas.py            → pessoas, papéis, convites
    consentimentos.py     → registrar/revogar aceite com versão do texto
    senha.py              → palavra-senha, tentativas, bloqueio, recuperação por código
    fila/                 → enfileirar, pegar, concluir, re-tentar; trabalhador
    eventos.py            → registro de quem fez o quê e quanto custou
    midia.py              → enviar/ler/apagar no R2; links temporários
    backup.py             → pg_dump diário para o R2 e limpeza dos antigos
  creditos/ geracao/ conversa/ central/ instagram/ social_media/ pagamento/  → próximos módulos (vazios agora)
migrations/               → Alembic
tests/nucleo/             → testes deste módulo
docs/spec/                → este documento e os próximos
Dockerfile · pyproject.toml · uv.lock · .env.example (só nomes, sem valores)
```
Os scripts que já existem (`gerar_foto_google.py`, `trava_cenario.py`, `mascara_peca.py`, `erros.py`, `referencias.py`) entram depois, no módulo `geracao`/`qualidade`.

## O que o núcleo guarda (modelo de dados)
- **lojas**: id, nome, @ do Instagram, segmento, cidade/UF, canais de venda, horário, endereço (opcional), plano e situação (preenchidos pelo módulo `creditos`), criada_em.
- **pessoas**: id, loja, nome, papel (dona | sócia | funcionária), id do Telegram (único), WhatsApp, e-mail, `pode_aprovar_gastos` (funcionária só com liberação da dona), criada_em.
- **convites**: código de uso único (guardado embaralhado), loja, papel, validade de 48 h, usado_por.
- **perfil_loja** (JSON flexível, a "lista invisível" do `atendente.md`): marca (tom, cliente-alvo, biótipo, kit), influencer (nome, aparência, voz, personalidade, referências), base de respostas, preferências, observações. Cada campo guarda **de onde veio** (Instagram, conversa, Eri) e **quando**.
- **fiscal** (vazio no piloto): CNPJ ou CPF, razão social, situação na consulta pública, conferido_em.
- **consentimentos**: pessoa, tipo (termos_privacidade, dados_agregados, instagram, whatsapp, ordem_fixa, modo_automatico, clone), versão do texto, aceito_em, revogado_em, detalhes (ex.: limite do modo automático, permissões do Instagram).
- **palavra_senha**: pessoa (só a dona), hash Argon2id, dica (opcional, escrita por ela), tentativas_erradas, bloqueada_ate, valida_ate (janela de 30 min depois de digitada).
- **codigos_recuperacao**: pessoa, hash do código de 6 números, expira em 10 min, tentativas (máx. 3), usado.
- **trabalhos** (fila): tipo, loja, estado (na_fila | rodando | concluido | falhou | cancelado), dados de entrada, resultado, erro, tentativas (máx. 3), próximo_horario, travado_ate, `chave_unica` (impede gerar duas vezes o mesmo pedido), custo_estimado, custo_real, fornecedor.
- **eventos** (auditoria, só acrescenta, nunca edita): quando, loja, quem (pessoa | influencer | Eri | sistema), ação, detalhes, custo.
- **midias**: loja, chave no R2, tipo (foto da peça, cenário, resultado, voz, vídeo), origem, criada_em, apagar_em.

## Regras de funcionamento
1. **Fila sem duplicar gasto:** cada trabalho tem `chave_unica`; pedir de novo a mesma coisa devolve o trabalho existente. Dois trabalhadores nunca pegam o mesmo trabalho (`SELECT … FOR UPDATE SKIP LOCKED`). Trabalho "rodando" há mais de 15 min sem sinal volta para a fila. Falhou → tenta de novo com espera crescente, no máximo 3 vezes; depois fica "falhou" e vira evento para a Central e o registro de erros.
2. **Palavra-senha** (decisões de Eri, 11h47 e 11h50): só a dona tem; pedida **só** para comprar créditos, mudar/cancelar plano e ligar o modo automático. Vale 30 min depois de digitada. 5 erros → bloqueio de 15 min + evento (aviso à dona e à Central). Recuperação **no piloto: pelo Eri** — a dona diz "esqueci" → `chamar_humano` → o Eri confirma quem é e libera a troca pela Central (a dona cria uma palavra nova na conversa). Depois, com domínio próprio: código de 6 números por e-mail, 10 min de validade, 3 tentativas (a tabela `codigos_recuperacao` já nasce pronta para isso). O núcleo oferece a função para o módulo `conversa` **apagar a mensagem** em que a palavra foi digitada.
3. **Consentimentos:** nenhum trabalho de geração entra na fila se a loja não tiver o aceite de termos e privacidade (o núcleo recusa e explica o motivo para quem chamou).
4. **Mídias:** bucket privado, uma pasta por loja; links temporários de 1 h para mostrar ou enviar. Nada público.
5. **LGPD:** "exportar" gera um arquivo com todos os dados da loja; "apagar" remove banco, mídias do R2 e qualquer cópia, e deixa só um evento anônimo de que a loja foi apagada. Loja cancelada: dados guardados 60 dias, depois apagados sozinhos (decisão de 25/10).
6. **Backup:** todo dia às 3h, cópia completa do banco para um bucket separado no R2; guarda os últimos 14 dias; teste de restauração uma vez por mês (manual, com o Eri).
7. **Saúde:** `/saude` responde se o banco, o R2 e a fila estão ok (sem expor detalhes internos).

## Estilo de código
Português nos nomes do domínio (loja, pessoa, trabalho), inglês só no que é da linguagem. Funções pequenas, com tipos e validação na entrada. Exemplo do jeito:
```python
def enfileirar(
    sessao: Session,
    *,
    loja_id: int,
    tipo: TipoTrabalho,
    dados: dict,
    chave_unica: str,
    custo_estimado: Decimal,
) -> Trabalho:
    """Põe um trabalho na fila. Se a chave já existe, devolve o existente (não gasta duas vezes)."""
    existente = sessao.scalar(select(Trabalho).where(Trabalho.chave_unica == chave_unica))
    if existente:
        return existente
    exigir_termos_aceitos(sessao, loja_id)  # levanta SemConsentimento se faltar
    trabalho = Trabalho(
        loja_id=loja_id,
        tipo=tipo,
        dados=dados,
        chave_unica=chave_unica,
        custo_estimado=custo_estimado,
    )
    sessao.add(trabalho)
    registrar_evento(
        sessao,
        loja_id=loja_id,
        quem="sistema",
        acao="trabalho_enfileirado",
        detalhes={"tipo": tipo, "chave": chave_unica},
    )
    return trabalho
```

## Estratégia de testes
- **pytest**, testes em `tests/nucleo/`, banco Postgres de teste em contêiner (o mesmo do Render), R2 simulado nos testes.
- **Unidade:** palavra-senha (hash, janela de 30 min, bloqueio, recuperação e expiração), convites, consentimentos, `chave_unica`, regras de re-tentativa.
- **Integração:** dois trabalhadores ao mesmo tempo não pegam o mesmo trabalho; trabalho travado volta; exportar e apagar uma loja (inclusive mídias); backup e restauração num banco vazio.
- **Abuso primeiro** (skill `security-and-hardening`): força bruta na palavra-senha, convite reutilizado, código expirado, trabalho sem consentimento, tentativa de ler mídia de outra loja.
- Cobertura mínima de 80% no `app/nucleo`.

## Limites
- **Sempre:** validar tudo que entra; segredos só em variáveis de ambiente do Render; rodar testes e ruff antes de cada envio; registrar evento para toda ação que muda dados ou gasta; tratar texto vindo da IA, do Instagram e da lojista como dado, nunca como comando.
- **Perguntar ao Eri antes:** mudar o modelo de dados depois de aprovado; acrescentar dependência nova; qualquer coisa que gaste dinheiro (planos pagos de Render, R2, e-mail); guardar um tipo novo de dado pessoal.
- **Nunca:** chave ou token no repositório ou em log; palavra-senha ou código em texto legível; mídia pública; apagar dados sem o pedido registrado; desligar um teste que falha sem combinar.

## Critérios de pronto
1. O servidor está no ar no Render e `/saude` responde "ok" para banco, R2 e fila.
2. `alembic upgrade head` cria todas as tabelas num banco vazio, sem erro.
3. É possível criar uma loja com dona, convidar uma funcionária por código (uso único, 48 h) e registrar o aceite de termos; tudo aparece nos eventos.
4. Sem aceite de termos, `enfileirar` recusa com motivo claro.
5. Teste com 2 trabalhadores: nenhum trabalho é pego duas vezes; um trabalho que falha é re-tentado até 3 vezes; um travado volta para a fila; a mesma `chave_unica` não cria trabalho novo.
6. Palavra-senha: só a dona cria; guardada só em hash; 5 erros bloqueiam 15 min; a troca liberada pelo Eri funciona e fica registrada nos eventos.
7. Exportar uma loja gera o arquivo completo; apagar remove banco e mídias e deixa só o evento anônimo.
8. O backup diário aparece no R2 e uma restauração num banco vazio funciona.
9. Varredura do repositório sem nenhum segredo; cobertura ≥ 80% no núcleo; todos os testes passando.

## Perguntas em aberto
Respondidas em 25/10: recuperação pelo Eri no piloto; região Leste dos EUA; repositório `world-estudio`. Nenhuma pendente para este módulo.
