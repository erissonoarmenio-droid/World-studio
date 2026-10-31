"""30/10 19h: cenas 2–5 pelo nó, 2.0 fast 720p (Eri: 'ótimo')."""
import json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pydantic import SecretStr
sys.path.insert(0, "/home/claude/world-studio"); sys.path.insert(0, "/home/claude/teste-no/v3")
from cenas_v3 import CENAS
from app.geracao.fornecedores.atlas import Atlas
from app.geracao.nos.envio import Aprovacao, RegistroEmMemoria, enviar
from app.geracao.nos.video import EntradaVideo, NoVideo
K = SecretStr(re.search(r"apikey-[a-z0-9]+", open("/mnt/user-data/uploads/6370b5dd-api.txt").read()).group(0))
D = "/mnt/user-data/uploads/TESTE INFLUENCER/trabalho/"
atlas, no, reg = Atlas(K), NoVideo(), RegistroEmMemoria()
OK = Aprovacao(por="eri 30/10 19h11 ('ótimo')", custo_max=Decimal("1.50"))
def um(c):
    img = atlas.subir_midia(open(D + f"{c}.png", "rb").read(), f"{c}.png", "image/png")
    aud = atlas.subir_midia(open(f"/home/claude/teste-no/v3/voz_{c}.wav", "rb").read(), f"{c}.wav", "audio/wav")
    pedido, rel = no.preparar(EntradaVideo(**CENAS[c], resolucao="720p", imagem_url=img, audio_url=aud))
    r = enviar(no, pedido, OK, atlas, reg); t = time.time()
    while r.estado == "na_fila" and time.time() - t < 900:
        time.sleep(10); r = enviar(no, pedido, OK, atlas, reg)
    preco = atlas._cliente.get(f"https://api.atlascloud.ai/api/v1/model/prediction/{r.id}", headers=atlas._cabecalho).json()["data"].get("price")
    return c, r.id, r.estado, r.saidas, r.erro, preco, rel.resumo().splitlines()[0]
with ThreadPoolExecutor(2) as ex: res = list(ex.map(um, ["c2", "c3", "c4", "c5"]))
for x in res: print(x[0], x[2], x[4], "US$", x[5], "|", x[6])
json.dump(res, open("/home/claude/teste-no/v3/res_v3.json", "w"), indent=1)
