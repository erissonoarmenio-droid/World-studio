# uso: python3 gfoto.py cena saida.png ref1.jpg [ref2.jpg]
import base64, json, os, sys, urllib.request, urllib.error
K = open(os.path.expanduser("~/.gk")).read().strip()
c, saida, refs = sys.argv[1], sys.argv[2], sys.argv[3:]
base = open("base.txt", encoding="utf-8").read().strip()
extra = (" Image 2 = the same woman in an earlier photo of this shoot: match this face exactly."
         if len(refs) > 1 else "")
p = base + extra + " She is 25 years old; keep her youthful 25-year-old face, do not age her. " + open(f"{c}.txt", encoding="utf-8").read().strip()
parts = [{"text": p}] + [{"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(open(r, "rb").read()).decode()}} for r in refs]
body = {"contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "9:16", "imageSize": "1K"}}}
req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/gemini-nano-banana-2.1:generateContent",
                             json.dumps(body).encode(), {"x-goog-api-key": K, "Content-Type": "application/json"})
try: r = json.load(urllib.request.urlopen(req, timeout=170))
except urllib.error.HTTPError as e: sys.exit(f"{c} erro {e.code}: {e.read()[:300]}")
for part in r["candidates"][0]["content"]["parts"]:
    if "inlineData" in part:
        open(saida, "wb").write(base64.b64decode(part["inlineData"]["data"])); print(c, "ok"); break
else: print(c, "sem imagem", r["candidates"][0].get("finishReason"))
