# 30/10: selfie nova (de cima, braço fora) pelo nó de foto, Google em lote, 2 opções.
import base64, json, os, time, urllib.request
K = open(os.path.expanduser("~/.gk")).read().strip()
B = "https://generativelanguage.googleapis.com/v1beta"
def call(m, url, body=None):
    r = urllib.request.Request(url, json.dumps(body).encode() if body else None, {"x-goog-api-key": K, "Content-Type": "application/json"}, method=m)
    return json.load(urllib.request.urlopen(r, timeout=18))
if os.path.exists("lote_selfie2.txt"):
    nome = open("lote_selfie2.txt").read().strip()
else:
    p = json.load(open("selfie_pedido.json"))
    reqs = [{"request": p, "metadata": {"key": f"s{i}"}} for i in (1, 2)]
    nome = call("POST", B + "/models/gemini-nano-banana-2.1:batchGenerateContent", {"batch": {"display_name": "selfie-c1-v2", "input_config": {"requests": {"requests": reqs}}}})["name"]
    open("lote_selfie2.txt", "w").write(nome); print("lote", nome, flush=True)
for i in range(15):
    l = call("GET", B + "/" + nome)
    if l.get("done"): break
    time.sleep(10)
print(l.get("metadata", {}).get("state"), l.get("done"))
if l.get("done"):
    for x in l["response"]["inlinedResponses"]["inlinedResponses"]:
        k = x["metadata"]["key"]
        for part in x["response"]["candidates"][0]["content"]["parts"]:
            if "inlineData" in part:
                open(f"selfie2_{k}.png", "wb").write(base64.b64decode(part["inlineData"]["data"])); print(k, "ok")
