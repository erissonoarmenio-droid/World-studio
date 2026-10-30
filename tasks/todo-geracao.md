# Tarefas: `geracao` parte 1 — os nós

Spec: `docs/spec/SPEC-geracao.md` · Plano: `tasks/plan-geracao.md`. Verificação padrão de cada tarefa: `uv run pytest -q tests/geracao` + `uv run ruff check .`.

- [x] **1. Contrato comum e regras** (S)
  - Aceite: `base.py` com Entrada, Pedido, Relatorio, Regra (id, nível bloqueia/aviso, faca, origem, checar), Veredito e erro `SemAprovacao`; `regras.py` com `--listar`; `httpx` no `pyproject.toml`.
  - Verificar: teste de uma regra que bloqueia e de uma que só avisa; `--listar` imprime origem.
  - Arquivos: `app/geracao/nos/base.py`, `app/geracao/nos/regras.py`, `pyproject.toml`, `tests/geracao/test_base.py`.

- [x] **2. Nó vídeo: montar e checar** (M)
  - Aceite: monta o prompt pelos 12 blocos (v2 de 29/10) só com entradas (fala, cena, duração, formato); regras E11 (fala entre aspas idêntica ao roteiro; "not its words"; papéis @image1/@audio1), E12 (five fingers), palavras proibidas, fala cabe (2,5 pal/s), enquadramento possível, sem `negative_prompt`.
  - Verificar: **o prompt v1 de 29/10 é bloqueado com motivo E11; os 5 prompts v2 passam.**
  - Arquivos: `app/geracao/nos/video.py`, `tests/geracao/casos/video_*.json`, `tests/geracao/test_no_video.py`.

- [x] **3. Nó voz: montar, checar e limites** (S)
  - Aceite: receita fixa da pesquisa (preâmbulo + PERFORMANCE + TRANSCRIPT), voz do cardápio; regras E3 (reticências), E2 (conector), fala cabe; função de conferência: palavras ≥ 90% e duração ≤ 1,8×.
  - Verificar: falas com "..." bloqueadas; as 5 falas finais de 29/10 passam; os resultados medidos de 29/10 (lendo instrução, 28 s) reprovam na conferência.
  - Arquivos: `app/geracao/nos/voz.py`, `tests/geracao/test_no_voz.py`.

### Parada A (depois de 1–3): Eri vê `--listar` e os testes do caso v1 barrado.

- [ ] **4. Envio único com aprovação + fornecedores** (M)
  - Aceite: `enviar(pedido, aprovacao)` levanta `SemAprovacao` sem ok; grava o id do fornecedor; segunda chamada só consulta o status; clientes `google.py` (inclui modo lote), `atlas.py` (upload de mídia + generate + consulta), `decart.py`; chaves só pelo config.
  - Verificar: testes com fornecedor simulado (sem rede): sem aprovação → erro; erro 503 → não reenvia, consulta status.
  - Arquivos: `app/geracao/nos/base.py`, `app/geracao/fornecedores/{google,atlas,decart}.py`, `app/config.py`, `tests/geracao/test_envio.py`.

- [ ] **5. Nó foto (Google só)** (S)
  - Aceite: blocos do `diretor-foto`; regras E5 (âncora na sequência + idade), E6 (cena de mãos), E7 (um espelho só), E15 (fornecedor ≠ Atlas).
  - Verificar: sequência sem âncora bloqueada; pedido pela Atlas recusado; os 5 pedidos que funcionaram em 29/10 passam.
  - Arquivos: `app/geracao/nos/foto.py`, `tests/geracao/test_no_foto.py`.

- [ ] **6. Nó juiz** (M)
  - Aceite: vereditos de foto, voz e vídeo com os limites da spec; transcrição só do áudio no vídeo.
  - Verificar: com as respostas gravadas de 29–30/10, a foto 2 da Atlas (6 dedos) reprova, as fotos do Google passam, os clipes v1 reprovam pela fala.
  - Arquivos: `app/geracao/nos/juiz.py`, `tests/geracao/casos/juiz_*.json`, `tests/geracao/test_no_juiz.py`.

### Parada B (depois de 4–6): Eri revê; decide se roda o teste real.

- [ ] **7. Nós vestir e lipsync (reserva)** (S)
  - Aceite: só rodam com veredito do juiz apontando peça alterada (vestir) ou fala errada (lipsync); regra de foto da peça (fundo liso, ≥ 512 px) e de áudio ≤ vídeo.
  - Verificar: chamada sem veredito → bloqueada.
  - Arquivos: `app/geracao/nos/vestir.py`, `app/geracao/nos/lipsync.py`, `tests/geracao/test_reservas.py`.

- [ ] **8. Ligar na fila e fechamento** (M)
  - Aceite: o trabalhador chama o nó pelo tipo (`foto`, `voz`, `video`); eventos para bloqueio, envio e veredito; cobertura ≥ 80% em `app/geracao`; varredura sem segredo.
  - Verificar: teste de integração com a fila (Postgres local) e fornecedor simulado; `uv run pytest -q` inteiro passando.
  - Arquivos: `app/nucleo/fila/trabalhador.py`, `app/geracao/__init__.py`, `tests/geracao/test_integracao.py`.

### Parada final: critérios de pronto da spec + teste real com gasto (só com ok do Eri).
