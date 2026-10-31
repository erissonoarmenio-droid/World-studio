import base64, json, os, glob, time, urllib.request, urllib.error, re
from concurrent.futures import ThreadPoolExecutor
K = open(os.path.expanduser("~/.gk")).read().strip()
U = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
P = ("Você vai ouvir um áudio curto em português. Pode ser uma pessoa real gravando um story no celular ou uma voz sintética. "
     "Avalie sem pressupor nada. Responda SÓ um JSON: {\"nota_natural\": 0-10 (10 = certamente pessoa real falando com amiga), "
     "\"parece\": \"pessoa real\"|\"locutora\"|\"voz de IA\", \"defeito_principal\": \"...\"}")
def call(body):
    for t in range(5):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(U, json.dumps(body).encode(), {"x-goog-api-key": K, "Content-Type": "application/json"}), timeout=90))
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(15 * (t + 1)); continue
            raise
def um(w):
    r = call({"contents": [{"parts": [{"text": P}, {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(open(w, "rb").read()).decode()}}]}],
              "generationConfig": {"responseMimeType": "application/json"}})
    try: j = json.loads(r["candidates"][0]["content"]["parts"][0]["text"])
    except Exception: j = {"erro": str(r)[:100]}
    j["arquivo"] = os.path.basename(w); return j
ws = sorted(glob.glob("comp31_*.wav"))
with ThreadPoolExecutor(2) as ex: res = list(ex.map(um, ws))
json.dump(res, open("juiz_nat31.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for x in res: print(x.get("arquivo"), x.get("nota_natural"), x.get("parece"), "|", str(x.get("defeito_principal"))[:80])
