"""Teste do R2 no ar (tarefa 11). Rodar no Shell do Render:

    python -m app.ferramentas.teste_r2

Cria duas lojas temporárias, envia uma imagem pequena para a primeira, confere
que ela lê, que o link temporário funciona e que a segunda loja NÃO consegue
ler. No fim apaga a imagem e as duas lojas. Custo: frações de centavo.
"""

import sys
import urllib.request
import uuid

from app.nucleo.db import sessao
from app.nucleo.erros import NaoEncontrado
from app.nucleo.eventos import ERI
from app.nucleo.lojas import criar_loja_com_dona
from app.nucleo.midia import apagar, armazenamento_midias, enviar, ler, link_temporario
from app.nucleo.modelos import Loja

# PNG de 1x1 pixel.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478"
    "da63f8cfc0f01f0005000201a5f3c0e40000000049454e44ae426082"
)


def main() -> int:
    marca = uuid.uuid4().hex[:8]
    with sessao() as s:
        a, _ = criar_loja_com_dona(s, {"nome": f"Teste R2 A {marca}"}, {"nome": "Teste A"}, ERI)
        b, _ = criar_loja_com_dona(s, {"nome": f"Teste R2 B {marca}"}, {"nome": "Teste B"}, ERI)
        loja_a, loja_b = a.id, b.id
    passos: list[tuple[str, bool]] = []
    diagnostico = armazenamento_midias().diagnostico()
    passos.append((f"chave e bucket respondem ({diagnostico})", diagnostico == "ok"))
    try:
        with sessao() as s:
            midia = enviar(
                s,
                loja_id=loja_a,
                conteudo=PNG,
                tipo="outro",
                content_type="image/png",
                origem="teste",
                autor=ERI,
            )
            midia_id, chave = midia.id, midia.chave
        passos.append((f"enviou para {chave}", True))

        with sessao() as s:
            passos.append(("a loja dona lê o arquivo", ler(s, midia_id, loja_a) == PNG))
            url = link_temporario(s, midia_id, loja_a)
        with urllib.request.urlopen(url, timeout=15) as resposta:  # noqa: S310 (link do R2)
            passos.append(("o link temporário abre", resposta.read() == PNG))

        with sessao() as s:
            try:
                ler(s, midia_id, loja_b)
                passos.append(("outra loja NÃO lê", False))
            except NaoEncontrado:
                passos.append(("outra loja NÃO lê", True))

        with sessao() as s:
            apagar(s, midia_id, loja_a, ERI)
        sobrou = armazenamento_midias().listar(chave)
        passos.append(("apagou do R2", not sobrou))
    except Exception as erro:
        passos.append((f"erro: {type(erro).__name__}", False))
    finally:
        with sessao() as s:
            for loja_id in (loja_a, loja_b):
                s.delete(s.get(Loja, loja_id))

    for texto, ok in passos:
        print(("OK    " if ok else "FALHOU ") + texto)
    tudo = all(ok for _, ok in passos)
    print("R2 funcionando." if tudo else "Algo falhou: me mande este resultado.")
    return 0 if tudo else 1


if __name__ == "__main__":
    sys.exit(main())
