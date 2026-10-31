# Juiz das cenas 1, 2, 4, 5 (30/10) em lote: vídeo sem a fala esperada + transcrição só do áudio.
import base64, json, os, time, urllib.request
K = open(os.path.expanduser("~/.gk")).read().strip()
B = "https://generativelanguage.googleapis.com/v1beta"
def b64(p): return base64.b64encode(open(p, "rb").read()).decode()
PV = 'Imagem 1 = referência da pessoa. O vídeo é um clipe UGC de loja gerado por IA. Assista com atenção, quadro a quadro, e seja rigoroso. Responda SÓ JSON: {"sincronia_boca": 0-10, "mesma_pessoa_do_inicio_ao_fim": 0-10, "parecida_com_referencia": 0-10, "idade_aparente": n, "maos_ok": true/false, "camisa_igual_o_tempo_todo": true/false, "espelho_ok": true/false/null, "texto_ou_logo": true/false, "celular_visivel_indevido": true/false, "musica": true/false, "parece_video_real": 0-10, "defeitos": ["segundo X: ..."]}'
PT = 'Transcreva EXATAMENTE o que é falado, palavra por palavra, sem corrigir. Só a transcrição.'
reqs = []
import sys
CENA = sys.argv[1]
for c in [CENA]:
    reqs.append({"request": {"contents": [{"parts": [{"text": PV}, {"inlineData": {"mimeType": "image/jpeg", "data": b64("influencer.jpg")}}, {"inlineData": {"mimeType": "video/mp4", "data": b64(f"v2_{c}_juiz.mp4")}}]}], "generationConfig": {"responseMimeType": "application/json"}}, "metadata": {"key": c + "_video"}})
    reqs.append({"request": {"contents": [{"parts": [{"text": PT}, {"inlineData": {"mimeType": "audio/mp3", "data": b64(f"audio_v2_{c}.mp3")}}]}]}, "metadata": {"key": c + "_audio"}})
def call(m, url, body=None):
    r = urllib.request.Request(url, json.dumps(body).encode() if body else None, {"x-goog-api-key": K, "Content-Type": "application/json"}, method=m)
    return json.load(urllib.request.urlopen(r, timeout=18))
if os.path.exists(f"lote_juiz_{CENA}.txt"):
    nome = open(f"lote_juiz_{CENA}.txt").read().strip()
else:
    nome = call("POST", B + "/models/gemini-3.8-flash:batchGenerateContent", {"batch": {"display_name": "juiz-resto", "input_config": {"requests": {"requests": reqs}}}})["name"]
    open(f"lote_juiz_{CENA}.txt", "w").write(nome); print("lote", nome)
for i in range(14):
    l = call("GET", B + "/" + nome)
    if l.get("done"): break
    time.sleep(10)
print(l.get("metadata", {}).get("state"), l.get("done"))
if l.get("done"):
    out = {}
    for x in l["response"]["inlinedResponses"]["inlinedResponses"]:
        out[x["metadata"]["key"]] = x["response"]["candidates"][0]["content"]["parts"][0]["text"]
    json.dump(out, open(f"juiz_{CENA}_v2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1); print(json.dumps(out, ensure_ascii=False))
