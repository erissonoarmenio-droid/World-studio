# Juiz das fotos: compara cada foto com a referência. Uso: python3 juiz_foto.py ref.jpg f1.png f2.png ...
import base64, json, os, sys, time, urllib.request, urllib.error
K = open(os.path.expanduser("~/.gk")).read().strip()
U = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
P = ("Imagem 1 = referência da pessoa. Imagem 2 = foto gerada para um vídeo UGC de loja. Seja rigoroso e não suponha nada. "
     "Responda SÓ JSON: {\"mesma_pessoa\": 0-10, \"idade_ref\": n, \"idade_foto\": n, \"maos_ok\": true/false, "
     "\"dedos_contados\": \"...\", \"espelho_reflexo_ok\": true/false/null, \"texto_ou_logo\": true/false, "
     "\"parece_foto_real\": 0-10, \"defeitos\": [\"...\"]}")
def img(p): return {"inlineData": {"mimeType": "image/png" if p.endswith("png") else "image/jpeg", "data": base64.b64encode(open(p, "rb").read()).decode()}}
ref = sys.argv[1]; out = []
for f in sys.argv[2:]:
    for t in range(4):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(U, json.dumps({"contents": [{"parts": [{"text": P}, img(ref), img(f)]}],
                "generationConfig": {"responseMimeType": "application/json"}}).encode(), {"x-goog-api-key": K, "Content-Type": "application/json"}), timeout=90)); break
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(15); continue
            raise
    j = json.loads(r["candidates"][0]["content"]["parts"][0]["text"]); j["foto"] = f; out.append(j); print(json.dumps(j, ensure_ascii=False))
json.dump(out, open("juiz_foto.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
