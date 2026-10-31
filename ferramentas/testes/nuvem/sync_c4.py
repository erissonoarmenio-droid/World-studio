"""30/10: Sync-3 na cena 4 (juiz Gemini: palavras 80%; Eri: 'pode ser sync-3')."""
import json, re, sys, time
from decimal import Decimal
from pydantic import SecretStr
sys.path.insert(0, "/home/claude/world-studio")
from app.geracao.fornecedores.atlas import Atlas
from app.geracao.nos.base import No, Pedido, Regra
from app.geracao.nos.envio import Aprovacao, RegistroEmMemoria, enviar
K = SecretStr(re.search(r"apikey-[a-z0-9]+", open("/mnt/user-data/uploads/6370b5dd-api.txt").read()).group(0))
atlas = Atlas(K)
class NoLipsyncTeste(No):
    nome = "lipsync"
    regras = (Regra("lipsync.audio_nao_maior", "bloqueia", "áudio ≤ vídeo", "spec nó lipsync",
                    lambda p: p.entrada["audio_s"] <= p.entrada["video_s"]),
              Regra("lipsync.com_veredito", "bloqueia", "só com o juiz apontando fala errada", "spec",
                    lambda p: p.entrada["veredito"] == "palavras 80% < 90%"),)
vurl = atlas.subir_midia(open("v2_c4.mp4", "rb").read(), "v2_c4.mp4", "video/mp4")
aurl = atlas.subir_midia(open("voz_c4_6s.wav", "rb").read(), "voz_c4.wav", "audio/wav")
p = Pedido(no="lipsync", fornecedor="atlas", modelo="sync/lipsync-v3",
           entrada={"audio_s": 6.0, "video_s": 6.08, "veredito": "palavras 80% < 90%"},
           payload={"model": "sync/lipsync-v3", "video_url": vurl, "audio_url": aurl, "sync_mode": "cut_off"},
           custo_estimado=Decimal("0.22") * 6)
no, reg = NoLipsyncTeste(), RegistroEmMemoria()
ok = Aprovacao(por="eri 30/10 15h10 (pode ser sync-3)", custo_max=Decimal("1.40"))
r = enviar(no, p, ok, atlas, reg); print("id", r.id, flush=True)
t = time.time()
while r.estado == "na_fila" and time.time() - t < 900:
    time.sleep(10); r = enviar(no, p, ok, atlas, reg)
print(r.estado, r.erro); json.dump({"id": r.id, "estado": r.estado, "saidas": r.saidas}, open("sync_c4.json", "w"))
