# Juiz de um clipe: transcrição só do áudio + juiz de vídeo sem a fala (thinkingBudget 0). Uso: juiz_um.py video.mp4 audio.mp3 saida.json
import base64, json, os, re, sys, urllib.request
K = open(os.path.expanduser("~/.gk")).read().strip()
U = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
PV = eval(re.search(r"^PV = (.*)$", open("juiz_cena_lote.py").read(), re.M).group(1))
PT = "Transcreva EXATAMENTE o que é falado, palavra por palavra, sem corrigir. Só a transcrição."
def b64(p): return base64.b64encode(open(p, "rb").read()).decode()
def call(parts, js):
    g = {"thinkingConfig": {"thinkingBudget": 0}}
    if js: g["responseMimeType"] = "application/json"
    r = json.load(urllib.request.urlopen(urllib.request.Request(U, json.dumps({"contents": [{"parts": parts}], "generationConfig": g}).encode(), {"x-goog-api-key": K, "Content-Type": "application/json"}), timeout=18))
    return r["candidates"][0]["content"]["parts"][0]["text"]
v, a, saida = sys.argv[1:4]
out = {"audio": call([{"text": PT}, {"inlineData": {"mimeType": "audio/mp3", "data": b64(a)}}], False).strip()}
print(out["audio"], flush=True)
out["video"] = json.loads(call([{"text": PV}, {"inlineData": {"mimeType": "image/jpeg", "data": b64("influencer.jpg")}}, {"inlineData": {"mimeType": "video/mp4", "data": b64(v)}}], True))
print(json.dumps(out["video"], ensure_ascii=False))
json.dump(out, open(saida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
