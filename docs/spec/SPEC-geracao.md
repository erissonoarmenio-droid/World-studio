# Spec: `geracao` — parte 1: os nós de geração

Versão 0.1 — 30/out/2026. Módulo `geracao` do mapa aprovado (`docs/spec/MAPA.md`), depende do `nucleo`. Esta parte cobre **só os nós** (o miolo que monta, trava, envia e confere cada geração). O débito de créditos fica para quando o módulo `creditos` existir; os nós já devolvem o custo estimado e o real para isso.

Base: `aios/projects/aprendizados-processo-video.md` (erros E1–E17 e regras 0–13), `claude/formula-prompt-seedance.md` v2.2, `claude/arquitetura-estudio-ugc.md` §7 (nós), estudo do Sirio de 30/10 (check file que bloqueia antes de gerar).

## Suposições (corrija agora, ou sigo com elas)
1. **Sem mudança no banco nesta parte.** Os nós são código puro, chamados pelo trabalhador da fila já existente com os tipos `foto`, `voz` e `video`. Os tipos novos (`vestir`, `lipsync`, `juiz`) entram numa migração na parte 2.
2. **Cliente HTTP `httpx`** (dependência nova — precisa do seu ok). Ele se identifica como `world-estudio/<versão>`; com isso a Atlas não barra o pedido (E10) sem disfarçar nada.
3. **No Render a rede não tem o corte de 20 s** que existe no seu computador (E16). O nó de foto chama o Google direto; o **modo em lote** fica como opção para pedidos que podem esperar (metade do preço).
4. **Mídias entram e saem pelo R2** (`app/nucleo/midia.py`), por chave; nada de arquivo público.
5. **Juízes no Gemini 3.8 Flash.** Voz padrão **Kore**, com a receita da pesquisa (versão 2, escolhida em 30/10).

## Objetivo
Acabar com o "prompt escrito à mão" (E11). Toda geração passa por um nó que:
1. recebe **só as entradas que mudam** (a peça, a fala, a cena, as referências);
2. junta as **partes fixas** (prompt-base pelo método, modelo, resolução, proporção);
3. roda a **lista de regras FAÇA / NÃO FAÇA com limites**, e **não envia nada** se uma regra que bloqueia falhar;
4. só envia com **aprovação explícita** e **um pedido só** (sem re-envio automático);
5. **confere o resultado** com o juiz antes de entregar.

Cada regra tem a **origem** (ex.: `E11 — 29/10`), para saber por que existe. Erro novo vira regra nova (melhoria contínua).

## Os nós

| Nó | Entradas (mudam) | Partes fixas | Fornecedor | Regras que bloqueiam (exemplos) |
|---|---|---|---|---|
| `foto` | ficha da peça, influencer (imagem), cena (formato F1–F12), foto âncora (opcional), idade | blocos do `diretor-foto`, `gemini-nano-banana-2.1`, 9:16, 1K/2K | **Google direto** (nunca Atlas — E15) | sequência sem foto âncora (E5); "mirror" sem "one single mirror" (E7); cena de mãos sem "five fingers" (E6); sem idade escrita (E5) |
| `voz` | fala, voz do cardápio | receita da pesquisa (preâmbulo + `### PERFORMANCE` + `#### TRANSCRIPT`), modelo TTS | Google TTS (troca para o modelo irmão se a cota acabar — E13) | fala com "..." (E3); começa com palavra solta sem conector (E2); fala que não cabe no tempo |
| `video` | fala do roteiro, foto da cena, áudio da voz, formato, duração | 12 blocos da fórmula, Seedance 2.0 fast, 480p, 9:16, `generate_audio` | Atlas | fala não está entre aspas ou difere do roteiro (E11); "words of audio" em vez de "not its words" (E11); sem `@image1`/`@audio1` com papel; sem "five fingers" (E12); palavra proibida; fala não cabe (2,5 pal/s); enquadramento impossível; `negative_prompt` |
| `vestir` (reserva) | vídeo, foto da peça (fundo liso, ≥ 512 px) | prompt "substitute…" com textura e cor, `lucy-vton-latest`, 720p | Decart | foto da peça fora do padrão; usado sem o juiz ter apontado peça alterada |
| `lipsync` (reserva) | vídeo, áudio exato | Sync-3 | Atlas | usado sem o juiz ter apontado fala errada; áudio maior que o vídeo |
| `juiz` | resultado + referências | prompts dos juízes de 29/10 | Gemini | — (só dá veredito) |

**Limites de aprovação dos juízes** (vindos das regras 2 e 4): foto — mesma pessoa ≥ 6, idade ±3, mãos ok, sem texto/logo, espelho coerente; voz — palavras ≥ 90% e duração ≤ 1,8× o esperado; vídeo — palavras ≥ 90% (transcrição só do áudio), peça igual, mãos ok, sem música/texto.

## Fluxo de um nó (contrato)
```
entrada (validada) → montar_pedido() → checar() ──falhou──→ BLOQUEADO (motivos + origem; não gasta)
                                         └──passou──→ aguarda aprovação → enviar() uma vez → conferir() → aprovado / reprovado (com motivo)
```
- `montar_pedido` e `checar` **não usam rede**: dá para testar tudo sem gastar.
- `enviar` sem aprovação levanta erro; com erro do fornecedor, consulta o status pelo id antes de qualquer novo envio (regra do Sirio: um pedido por geração).

## Tech stack
Python 3.12, Pydantic v2 (entradas e relatórios), `httpx` (suposição 2), o `nucleo` já existente (fila, eventos, mídia no R2). Nada novo no banco nesta parte.

## Comandos
```
Testes dos nós:   uv run pytest -q tests/geracao
Cobertura:        uv run pytest --cov=app/geracao --cov-report=term-missing
Estilo:           uv run ruff check --fix . && uv run ruff format .
Ver as regras:    uv run python -m app.geracao.nos.regras --listar   (imprime FAÇA/NÃO FAÇA de cada nó, com a origem)
```

## Estrutura do projeto
```
app/geracao/
  nos/
    base.py        → contrato comum: Entrada, Pedido, Relatorio, Regra, Veredito, erro SemAprovacao
    regras.py      → as listas FAÇA/NÃO FAÇA de cada nó (com origem E1–E17) + listagem
    foto.py  voz.py  video.py  vestir.py  lipsync.py  juiz.py
  fornecedores/
    google.py  atlas.py  decart.py   → só a chamada HTTP (chaves pelo config, nunca no código)
tests/geracao/
  casos/           → os pedidos reais de 29–30/10 (o prompt v1 que falhou, o v2 que passou, as falas com "...")
  test_regras_*.py, test_nos_*.py
```

## Estilo de código
O mesmo do núcleo (português no domínio, funções pequenas, tipos). Uma regra é assim:
```python
Regra(
    id="video.fala_entre_aspas",
    nivel="bloqueia",
    faca="A fala do roteiro vai entre aspas no prompt, idêntica ao roteiro.",
    origem="E11 — 29/10 (Seedance trocou as palavras em 4 de 5 clipes)",
    checar=lambda p: re.findall(r'"([^"]+)"', p.prompt) == [p.entrada.fala],
)
```

## Estratégia de testes
- **Casos reais primeiro:** o prompt de vídeo de 29/10 (v1) **tem que ser bloqueado** pela regra E11; o v2 tem que passar. As falas com "..." têm que ser bloqueadas. O pedido de foto pela Atlas tem que ser recusado.
- **Sem rede nos testes:** fornecedores simulados; nenhum teste gasta.
- **Abuso:** `enviar` sem aprovação; segundo envio do mesmo pedido; texto da lojista tentando mudar regra ("ignore as regras") é tratado como dado.
- Cobertura ≥ 80% em `app/geracao`.

## Limites
- **Sempre:** toda regra tem origem; `checar` antes de `enviar`; custo estimado em todo pedido; evento registrado para envio e veredito; chaves só no config.
- **Perguntar ao Eri antes:** dependência nova (`httpx`); migração com tipos novos de trabalho; trocar fornecedor ou modelo padrão; afrouxar ou remover uma regra que bloqueia.
- **Nunca:** enviar sem aprovação; re-enviar sozinho; foto pela Atlas; prompt montado fora do nó; chave em código ou log.

## Critérios de pronto
1. Os 6 nós existem com o contrato acima, e `--listar` mostra todas as regras com a origem.
2. O prompt de vídeo v1 de 29/10 é **bloqueado** com o motivo E11; o v2 **passa**.
3. A fala com reticências é bloqueada (E3); a receita da voz é sempre a da pesquisa.
4. Pedido de foto sem foto âncora numa sequência é bloqueado (E5); nó de foto nunca aceita a Atlas (E15).
5. Nenhum nó envia sem aprovação; nenhum re-envio automático (testado).
6. Os juízes devolvem veredito com os limites acima, testados com os resultados reais de 29–30/10 (falas, fotos e clipes já gerados).
7. Testes passando, cobertura ≥ 80%, sem segredo no repositório.

## Perguntas em aberto
1. Posso acrescentar a dependência `httpx`?
2. A parte 2 (migração com os tipos `vestir`, `lipsync` e `juiz` na fila + débito de créditos) fica para depois do módulo `creditos`?
