"""30/10: cenas 1, 2, 4, 5 pelo nó de vídeo, depois do clipe de teste c3 aprovado pelo juiz (ok de Eri)."""
import json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pydantic import SecretStr
sys.path.insert(0, "/home/claude/world-studio")
from app.geracao.fornecedores.atlas import Atlas
from app.geracao.nos.envio import Aprovacao, RegistroEmMemoria, enviar
from app.geracao.nos.video import EntradaVideo, NoVideo
K = SecretStr(re.search(r"apikey-[a-z0-9]+", open("/mnt/user-data/uploads/6370b5dd-api.txt").read()).group(0))
D = "/mnt/user-data/uploads/TESTE INFLUENCER/trabalho/"
V2 = json.load(open("/home/claude/world-studio/tests/geracao/casos/video_v2_2910.json"))["casos"]
FALA_S = {"c1": 7.3, "c2": 4.41, "c4": 4.2, "c5": 4.49}
DUR = {"c1": 9, "c2": 6, "c4": 6, "c5": 6}
atlas, no, reg = Atlas(K), NoVideo(), RegistroEmMemoria()
OK = Aprovacao(por="eri 30/10 15h10", custo_max=Decimal("0.70"))
def um(c):
    img = atlas.subir_midia(open(D + f"{c}.png", "rb").read(), f"{c}.png", "image/png")
    aud = atlas.subir_midia(open(D + f"comp31_D_{c}.wav", "rb").read(), f"{c}.wav", "audio/wav")
    campos = {k: V2[c][k] for k in ("fala", "objetivo", "formato", "cenario", "peca", "batidas", "tom", "vibe")}
    campos["formato"] = re.sub(r"^\d+ seconds", f"{DUR[c]} seconds", campos["formato"])
    e = EntradaVideo(**campos, duracao=DUR[c], imagem_url=img, audio_url=aud, audio_segundos=FALA_S[c])
    pedido, rel = no.preparar(e)
    r = enviar(no, pedido, OK, atlas, reg)
    t = time.time()
    while r.estado == "na_fila" and time.time() - t < 900:
        time.sleep(10); r = enviar(no, pedido, OK, atlas, reg)
    return c, str(pedido.custo_estimado), r.id, r.estado, r.saidas, r.erro, rel.resumo()
with ThreadPoolExecutor(2) as ex:
    res = list(ex.map(um, ["c1", "c2", "c4", "c5"]))
for x in res: print(x[0], x[1], x[2], x[3], x[5], "|", x[6].splitlines()[0])
json.dump(res, open("resultado_resto.json", "w"), ensure_ascii=False, indent=1)
