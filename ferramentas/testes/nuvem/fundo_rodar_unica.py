"""30/10 20h: tomada única no fundo da loja, 2 versões, Tein 2.0 fast 720p (modelo do Sirio: gerar e escolher)."""
import json, sys, time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pydantic import SecretStr
sys.path.insert(0, "/home/claude/world-studio")
from app.geracao.fornecedores.tein import Tein
from app.geracao.nos.envio import Aprovacao, RegistroEmMemoria, enviar
from app.geracao.nos.video import EntradaVideo, NoVideo
V2 = json.load(open("/home/claude/world-studio/tests/geracao/casos/video_v2_2910.json"))["casos"]
tein, no = Tein(SecretStr(open("/home/claude/.tein").read().strip())), NoVideo()
img = tein.subir_midia(open("primeiro_quadro.png", "rb").read(), "loja.png", "image/png")
aud = tein.subir_midia(open("voz_unica.wav", "rb").read(), "voz.wav", "audio/wav")
base = dict(
    fala=open("/mnt/user-data/outputs/fala_unica.txt").read().strip(), duracao=12, audio_segundos=10.1,
    objetivo="Create a talking clip from @image1.",
    formato=("12 seconds UGC style story, filmed on smartphone, soft store ceiling light, phone propped at chest height "
             "facing her, framing from the chest up, her face large in the frame; the propped phone wobbles slightly."),
    cenario=("The store room behind her stays exactly as in @image1: white sideboard, three gold-framed organic mirrors "
             "showing only the empty room, grey armchair, air conditioner on the wall."),
    peca=V2["c1"]["peca"],
    batidas=("The video opens with her standing still, facing the camera, head steady, and she says in Brazilian "
             "Portuguese: {fala} When she mentions the hands she briefly raises both open hands beside her face and "
             "lowers them; when she mentions the shirt she lightly touches its front. Final shot — silent, she smiles "
             "and holds the pose for the final second."),
    tom="The tone is playful, confident, warm — she takes a natural breath before speaking and never rushes.",
    vibe="The overall feel is real and fun — like a story she posted from the shop for her followers.",
    resolucao="720p", fornecedor="tein", imagem_url=img, audio_url=aud)
OK = Aprovacao(por="eri 30/10 20h05 (usa o fundo)", custo_max=Decimal("1.00"))
def um(i):
    e = EntradaVideo(**base)
    pedido, rel = no.preparar(e)
    # 2 versões do mesmo pedido: cada uma com sua chave (senão a Tein devolve a mesma geração)
    pedido = pedido.model_copy(update={"payload": pedido.payload | {"idempotency_key": f"unica-3010-v{i}"}})
    reg = RegistroEmMemoria(); r = enviar(no, pedido, OK, tein, reg); t = time.time()
    while r.estado == "na_fila" and time.time() - t < 900:
        time.sleep(10); r = enviar(no, pedido, OK, tein, reg)
    return i, rel.resumo().splitlines()[0], r.id, r.estado, r.saidas, r.custo, r.erro
with ThreadPoolExecutor(2) as ex: res = list(ex.map(um, [1, 2]))
for x in res: print(x[0], x[1], x[3], "US$", x[5], x[6])
json.dump(res, open("res_unica.json", "w"), indent=1)
