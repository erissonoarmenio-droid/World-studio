"""Teste real 30/10: cena 3 pelo nó de vídeo (aprovado por Eri: 'pode fazer')."""
import json, re, sys, time
from decimal import Decimal
from pydantic import SecretStr
sys.path.insert(0, "/home/claude/world-studio")
from app.geracao.fornecedores.atlas import Atlas
from app.geracao.nos.envio import Aprovacao, RegistroEmMemoria, enviar
from app.geracao.nos.video import EntradaVideo, NoVideo
K = SecretStr(re.search(r"apikey-[a-z0-9]+", open("/mnt/user-data/uploads/6370b5dd-api.txt").read()).group(0))
D = "/mnt/user-data/uploads/TESTE INFLUENCER/trabalho/"
V2 = json.load(open("/home/claude/world-studio/tests/geracao/casos/video_v2_2910.json"))["casos"]["c3"]
atlas = Atlas(K)
img = atlas.subir_midia(open(D + "c3.png", "rb").read(), "c3.png", "image/png")
aud = atlas.subir_midia(open(D + "comp31_D_c3.wav", "rb").read(), "c3.wav", "audio/wav")
campos = {k: V2[k] for k in ("fala", "objetivo", "formato", "cenario", "peca", "batidas", "tom", "vibe")}
campos["formato"] = campos["formato"].replace("6 seconds", "8 seconds")
e = EntradaVideo(**campos, duracao=8, imagem_url=img, audio_url=aud, audio_segundos=6.4)
no = NoVideo()
pedido, rel = no.preparar(e)
print("regras:", rel.resumo()); print("custo estimado US$", pedido.custo_estimado)
json.dump({"prompt": pedido.prompt, "payload": pedido.payload}, open("/home/claude/teste-no/pedido_c3.json", "w"), ensure_ascii=False, indent=1)
reg = RegistroEmMemoria()
r = enviar(no, pedido, Aprovacao(por="eri 30/10 15h10", custo_max=Decimal("0.60")), atlas, reg)
print("enviado id", r.id, flush=True)
t = time.time()
while r.estado == "na_fila" and time.time() - t < 600:
    time.sleep(10); r = enviar(no, pedido, Aprovacao(por="eri", custo_max=Decimal("0.60")), atlas, reg)
print(r.estado, r.saidas, r.erro)
open("/home/claude/teste-no/resultado.json", "w").write(json.dumps({"id": r.id, "estado": r.estado, "saidas": r.saidas}))
