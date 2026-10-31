import base64, json, os, urllib.request
K = open(os.path.expanduser("~/.gk")).read().strip()
U = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
P = ("Imagem 1 = referência da pessoa. Imagem 2 = foto gerada para um vídeo UGC de loja. Seja rigoroso e não suponha nada. "
     "Responda SÓ JSON: {\"mesma_pessoa\": 0-10, \"idade_ref\": n, \"idade_foto\": n, \"maos_ok\": true/false, "
     "\"dedos_contados\": \"...\", \"espelho_reflexo_ok\": true/false/null, \"texto_ou_logo\": true/false, "
     "\"parece_foto_real\": 0-10, \"pose_de_selfie_possivel\": true/false, \"defeitos\": [\"...\"]}")
def b64(p): return base64.b64encode(open(p, "rb").read()).decode()
body = {"contents": [{"parts": [{"text": P}, {"inlineData": {"mimeType": "image/jpeg", "data": b64("influencer.jpg")}}, {"inlineData": {"mimeType": "image/jpeg", "data": b64("selfie_c1_final.jpg")}}]}],
        "generationConfig": {"responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}}}
r = json.load(urllib.request.urlopen(urllib.request.Request(U, json.dumps(body).encode(), {"x-goog-api-key": K, "Content-Type": "application/json"}), timeout=18))
print(r["candidates"][0]["content"]["parts"][0]["text"])
