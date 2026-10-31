# 30/10: fotos do peito para cima (cenas 3 e 4) pelo nó de foto, Google em lote.
import base64, json, os, time, urllib.request, subprocess
K = open(os.path.expanduser("~/.gk")).read().strip()
B = "https://generativelanguage.googleapis.com/v1beta"
def call(m, url, body=None):
    r = urllib.request.Request(url, json.dumps(body).encode() if body else None, {"x-goog-api-key": K, "Content-Type": "application/json"}, method=m)
    return json.load(urllib.request.urlopen(r, timeout=18))
if os.path.exists("lote_peito.txt"): nome = open("lote_peito.txt").read().strip()
else:
    nome = call("POST", B + "/models/gemini-nano-banana-2.1:batchGenerateContent", {"batch": {"display_name": "peito", "input_config": {"requests": {"requests": json.load(open("peito_reqs.json"))}}}})["name"]
    open("lote_peito.txt", "w").write(nome); print("lote", nome, flush=True)
for i in range(12):
    l = call("GET", B + "/" + nome)
    if l.get("done") or (l.get("metadata") or {}).get("state") == "BATCH_STATE_SUCCEEDED": break
    time.sleep(10)
print((l.get("metadata") or {}).get("state"))
if (l.get("metadata") or {}).get("state") == "BATCH_STATE_SUCCEEDED":
    subprocess.run(["curl", "-s", "-m", "170", "-H", f"x-goog-api-key: {K}", f"{B}/{nome}", "-o", "peito.json"])
    l = json.load(open("peito.json"))
    for x in l["response"]["inlinedResponses"]["inlinedResponses"]:
        for p in x["response"]["candidates"][0]["content"]["parts"]:
            if "inlineData" in p: open(f"{x['metadata']['key']}.png", "wb").write(base64.b64decode(p["inlineData"]["data"])); print(x["metadata"]["key"], "ok")
