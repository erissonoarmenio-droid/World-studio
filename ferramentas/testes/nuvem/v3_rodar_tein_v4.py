"""30/10 19h30: 1 cena de teste (c2) pela Tein, 2.0 fast 720p (Eri pôs US$ 10 e passou a chave)."""
import json, sys, time
from decimal import Decimal
from pydantic import SecretStr
sys.path.insert(0, "/home/claude/world-studio"); sys.path.insert(0, "/home/claude/teste-no/v3")
from cenas_v3 import CENAS_V4 as CENAS
from app.geracao.fornecedores.tein import Tein
from app.geracao.nos.envio import Aprovacao, RegistroEmMemoria, enviar
from app.geracao.nos.video import EntradaVideo, NoVideo
cenas = sys.argv[1:] or ["c2"]
tein, no, reg = Tein(SecretStr(open("/home/claude/.tein").read().strip())), NoVideo(), RegistroEmMemoria()
OK = Aprovacao(por="eri 30/10 19h28 (chave + US$ 10)", custo_max=Decimal("1.00"))
D = "/mnt/user-data/uploads/TESTE INFLUENCER/trabalho/"
res = {}
for c in cenas:
    img = tein.subir_midia(open(D + f"{c}p.png", "rb").read(), f"{c}.png", "image/png")
    aud = tein.subir_midia(open(f"voz_{c}.wav", "rb").read(), f"{c}.wav", "audio/wav")
    pedido, rel = no.preparar(EntradaVideo(**CENAS[c], resolucao="720p", fornecedor="tein", imagem_url=img, audio_url=aud))
    print(c, rel.resumo().splitlines()[0], "estimado US$", pedido.custo_estimado, flush=True)
    r = enviar(no, pedido, OK, tein, reg); print(c, "id", r.id, flush=True)
    t = time.time()
    while r.estado == "na_fila" and time.time() - t < 900:
        time.sleep(10); r = enviar(no, pedido, OK, tein, reg)
    print(c, r.estado, r.erro, "cobrado US$", r.custo, flush=True)
    res[c] = {"id": r.id, "estado": r.estado, "saidas": r.saidas, "custo": r.custo, "erro": r.erro}
json.dump(res, open(f"res_tein_v4_{'_'.join(cenas)}.json", "w"), indent=1)
