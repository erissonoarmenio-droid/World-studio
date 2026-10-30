# Plano: `geracao` parte 1 — os nós

Spec: `docs/spec/SPEC-geracao.md` (aprovada por Eri em 30/10, 14h45, com `httpx` liberado; parte 2 — migração com tipos novos e débito de créditos — fica para depois do módulo `creditos`). Lista de tarefas: `tasks/todo-geracao.md`. O plano do núcleo (`tasks/plan.md`, `tasks/todo.md`) continua valendo e não foi alterado.

## Visão geral
Seis nós (foto, voz, vídeo, vestir, lipsync, juiz) com o mesmo contrato: entrada validada → `montar_pedido` → `checar` (regras FAÇA/NÃO FAÇA com origem; bloqueia sem gastar) → aprovação → `enviar` uma vez → `conferir` pelo juiz.

## Decisões de arquitetura
- **Contrato primeiro** (`base.py` + `regras.py`): todos os nós herdam o mesmo fluxo; a trava e a aprovação ficam num lugar só, não em cada nó.
- **`montar_pedido` e `checar` sem rede**: o grosso dos testes não gasta e roda rápido.
- **Fornecedores separados dos nós** (`fornecedores/`): trocar Atlas por Tein, ou Google por outro, não mexe nas regras.
- **Vídeo é o nó mais arriscado e o que mais custou** (E11): vem logo depois da base, para falhar cedo.
- **Casos reais de 29–30/10 como testes** (`tests/geracao/casos/`): o prompt v1 que trocou as falas, o v2, as falas com "...", os vereditos já medidos.

## Ordem (grafo de dependências)
```
1 base + regras ──┬── 2 vídeo (montar+checar)
                  ├── 3 voz (montar+checar+limites)
                  └── 4 envio único com aprovação + fornecedores
                           ├── 5 foto (Google só)
                           ├── 6 juiz
                           └── 7 vestir + lipsync (reserva)
                                    └── 8 ligar na fila + fechamento
```

## Riscos
| Risco | Impacto | Como reduzir |
|---|---|---|
| Regra de texto frágil (ex.: aspas tipográficas “ ” em vez de " ) deixa passar um prompt errado | Alto | Normalizar aspas e espaços antes de checar; casos de teste com as variações |
| Regra boa demais bloqueia prompt certo | Médio | Cada regra testada com 1 caso que passa e 1 que bloqueia |
| Formato da API do fornecedor muda (Atlas/Decart) | Médio | Fornecedor isolado + teste de contrato com resposta gravada; erro claro quando o formato mudar |
| Juiz (IA) varia entre execuções | Médio | Juiz só aprova/reprova com limites; nota de n pequeno é indício (regra 7); teste com respostas gravadas |
| Re-envio duplicado gasta duas vezes | Alto | `enviar` grava o id do fornecedor antes de qualquer nova tentativa; segunda chamada só consulta o status |

## Perguntas em aberto
- Nenhuma bloqueando. O teste com gasto real (1 foto + 1 voz + 1 vídeo pelos nós) fica para depois da tarefa 8, com o ok de Eri.
