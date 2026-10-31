# 30/10: voz da tomada única (receita D, Kore) em lote no Google, 2 opções.
import base64, json, os, time, urllib.request, subprocess
K = open(os.path.expanduser("~/.gk")).read().strip()
B = "https://generativelanguage.googleapis.com/v1beta"
M = "gemini-3.1-flash-tts-preview"
def call(m, url, body=None):
    r = urllib.request.Request(url, json.dumps(body).encode() if body else None, {"x-goog-api-key": K, "Content-Type": "application/json"}, method=m)
    return json.load(urllib.request.urlopen(r, timeout=18))
if os.path.exists("lote_voz_unica.txt"): nome = open("lote_voz_unica.txt").read().strip()
else:
    nome = call("POST", f"{B}/models/{M}:batchGenerateContent", {"batch": {"display_name": "voz-unica", "input_config": {"requests": {"requests": json.load(open("voz_unica_reqs.json"))}}}})["name"]
    open("lote_voz_unica.txt", "w").write(nome); print("lote", nome, flush=True)
for i in range(12):
    l = call("GET", B + "/" + nome)
    if (l.get("metadata") or {}).get("state") in ("BATCH_STATE_SUCCEEDED", "BATCH_STATE_FAILED"): break
    time.sleep(10)
print((l.get("metadata") or {}).get("state"))
if (l.get("metadata") or {}).get("state") == "BATCH_STATE_SUCCEEDED":
    subprocess.run(["curl", "-s", "-m", "160", "-H", f"x-goog-api-key: {K}", f"{B}/{nome}", "-o", "voz_unica.json"])
    l = json.load(open("voz_unica.json"))
    for x in l["response"]["inlinedResponses"]["inlinedResponses"]:
        k = x["metadata"]["key"]
        try: pcm = base64.b64decode(x["response"]["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
        except Exception as e: print(k, "sem audio", str(x)[:200]); continue
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0", f"voz_unica_{k}.wav"], input=pcm, check=True)
        print(k, "ok", round(len(pcm) / 48000, 2), "s")
