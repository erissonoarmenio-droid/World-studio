# Scripts de teste da geração (histórico, 29–30/10/2026)

Guardados aqui em 31/10/2026 para não se perderem (antes estavam só na nuvem da sessão e no computador de Eri). **São registros de testes, não o caminho oficial.** O caminho oficial são os nós em `app/geracao/nos/` (foto, voz, vídeo, juiz) com as regras que barram o pedido antes de gastar. Resultados e erros medidos: `aios/projects/aprendizados-processo-video.md` (projeto W-orld).

Nenhum script tem chave dentro: a do Google fica em `~/.gk` no computador de Eri, a da Tein em `~/.tein` na sessão. Nunca colocar chave neste repositório.

## Reaproveitar (ferramentas de medição)
| Script | Para que serve |
|---|---|
| `nuvem/medir.py` | Mede por quadro: identidade (SFace contra a referência), tremor do rosto e sincronia boca × áudio |
| `nuvem/tempo.py` | Identidade do rosto por quadro ao longo do clipe (YuNet + SFace) |
| `computador/juiz_um.py` | Juiz de um clipe: transcrição só do áudio + juiz de vídeo sem a fala esperada (thinkingBudget 0) |
| `computador/juiz_foto.py` | Juiz das fotos contra a referência |
| `computador/transcrever.py` | Transcrição de áudio pelo Gemini |
| `computador/*_lote.py` | Pedidos ao Google em modo lote (foto, voz, juiz) — o jeito que funciona pelo computador de Eri (E16) |

## Histórico (o que cada teste fez)
- `nuvem/fundo_rodar_unica.py`: tomada única no fundo da loja, 2 versões, Tein 720p (30/10 20h, **aprovado**).
- `nuvem/v3_*.py`, `nuvem/rodar_c3.py`, `nuvem/rodar_resto.py`: cenas separadas (E22/E23).
- `nuvem/selfie_*.py`: selfie Seedance 2.5 rascunho → 1080p / 720p.
- `nuvem/sync_c4.py`: Sync-3 (reprovado, E21).
- `computador/voz_*.py`, `gvoz*.py`, `exp_voz.py`: comparação das receitas de voz (receita D venceu).
- `computador/gfoto.py`, `peca.py`, `selfie_lote.py`, `peito_lote.py`, `fundo_lote.py`: fotos pelo Google.
- `computador/juiz_*.py`: versões do juiz de vídeo.
