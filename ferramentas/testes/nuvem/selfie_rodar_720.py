"""30/10: selfie nova pelo nó (E22: parada ao falar, rosto grande), Seedance 2.5 em rascunho 480p."""
import json, re, sys, time
from decimal import Decimal
from pydantic import SecretStr
sys.path.insert(0, "/home/claude/world-studio")
from app.geracao.fornecedores.atlas import Atlas
from app.geracao.nos.envio import Aprovacao, RegistroEmMemoria, enviar
from app.geracao.nos.video import MODELO, EntradaVideo, NoVideo
K = SecretStr(re.search(r"apikey-[a-z0-9]+", open("/mnt/user-data/uploads/6370b5dd-api.txt").read()).group(0))
V2 = json.load(open("/home/claude/world-studio/tests/geracao/casos/video_v2_2910.json"))["casos"]["c1"]
atlas = Atlas(K)
img = atlas.subir_midia(open("selfie_c1_final.png", "rb").read(), "selfie_c1.png", "image/png")
aud = atlas.subir_midia(open("voz_c1.wav", "rb").read(), "voz_c1.wav", "audio/wav")
e = EntradaVideo(
    fala=V2["fala"], duracao=8, modelo=MODELO, resolucao="720p",
    objetivo="Create a talking selfie clip from @image1.",
    formato=("8 seconds UGC style story, filmed on smartphone, warm boutique ceiling light, phone front camera "
             "selfie held at arm's length, framing from the shoulders up, her face large in the frame; the phone "
             "is not visible."),
    cenario="The fitting room behind her: linen curtain, wall hooks with hangers.",
    peca=V2["peca"],
    batidas=("The video opens with her looking straight into the lens with a relaxed smile, holding still, with "
             "only the slight handheld micro-movement of the phone. She keeps her head steady, facing the camera, "
             "and says in Brazilian Portuguese: {fala} Final shot — silent, she smiles showing her teeth and "
             "holds the pose for the final second."),
    tom=V2["tom"], vibe=V2["vibe"], imagem_url=img, audio_url=aud, audio_segundos=6.6)
no = NoVideo(); pedido, rel = no.preparar(e)
print(rel.resumo()); print("custo US$", pedido.custo_estimado); print(pedido.prompt)
json.dump({"prompt": pedido.prompt, "payload": pedido.payload}, open("pedido_720.json", "w"), ensure_ascii=False, indent=1)
reg, ok = RegistroEmMemoria(), Aprovacao(por="eri 30/10 19h04 (testa uma no 720p)", custo_max=Decimal("1.40"))
r = enviar(no, pedido, ok, atlas, reg); print("id", r.id, flush=True)
t = time.time()
while r.estado == "na_fila" and time.time() - t < 900:
    time.sleep(10); r = enviar(no, pedido, ok, atlas, reg)
print(r.estado, r.erro)
d = atlas._cliente.get(f"https://api.atlascloud.ai/api/v1/model/prediction/{r.id}", headers=atlas._cabecalho).json()["data"]
json.dump({k: d.get(k) for k in ("id", "status", "outputs", "draft", "draft_id", "price")}, open("res_720.json", "w"), indent=1)
print({k: d.get(k) for k in ("draft", "draft_id", "price")})
