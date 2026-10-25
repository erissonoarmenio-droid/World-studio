"""Teste da fila no ar (Parada C). Rodar no Shell do Render:

    python -m app.ferramentas.teste_fila

Cria uma loja temporária, põe um trabalho do tipo "teste" (não gasta nada),
espera o trabalhador do servidor concluir e apaga a loja temporária no fim.
"""

import sys
import time
import uuid

from app.nucleo.consentimentos import registrar_aceite
from app.nucleo.db import sessao
from app.nucleo.eventos import ERI, SISTEMA, Autor
from app.nucleo.fila import enfileirar
from app.nucleo.lojas import criar_loja_com_dona
from app.nucleo.modelos import Loja, Trabalho


def main(espera_max: float = 60.0) -> int:
    marca = uuid.uuid4().hex[:8]
    with sessao() as s:
        loja, dona = criar_loja_com_dona(
            s, {"nome": f"Teste da fila {marca}"}, {"nome": "Teste"}, ERI
        )
        registrar_aceite(s, dona.id, "termos_privacidade", "teste", Autor("pessoa", dona.id))
        trabalho, _ = enfileirar(
            s,
            loja_id=loja.id,
            tipo="teste",
            dados={"eco": marca},
            chave_unica=f"teste-fila-{marca}",
            autor=SISTEMA,
        )
        loja_id, trabalho_id = loja.id, trabalho.id
    print(f"Trabalho {trabalho_id} na fila. Esperando o trabalhador...")

    inicio, estado = time.monotonic(), "na_fila"
    try:
        while time.monotonic() - inicio < espera_max:
            with sessao() as s:
                t = s.get(Trabalho, trabalho_id)
                estado, resultado = t.estado, t.resultado
            if estado in ("concluido", "falhou"):
                break
            time.sleep(1)
        segundos = time.monotonic() - inicio
        if estado == "concluido" and resultado == {"ok": True, "eco": marca}:
            print(f"OK: concluído em {segundos:.1f} s pelo trabalhador do servidor.")
            return 0
        print(f"FALHOU: estado final '{estado}' depois de {segundos:.0f} s.")
        return 1
    finally:
        with sessao() as s:
            s.delete(s.get(Loja, loja_id))
        print("Loja temporária apagada.")


if __name__ == "__main__":
    sys.exit(main())
