"""30/10: termina em 1080p o rascunho aprovado pelo juiz (draft-complete, sem novo sorteio)."""
import json, re, time, httpx
K = re.search(r"apikey-[a-z0-9]+", open("/mnt/user-data/uploads/6370b5dd-api.txt").read()).group(0)
H = {"Authorization": f"Bearer {K}"}; B = "https://api.atlascloud.ai/api/v1/model"
c = httpx.Client(timeout=60)
if not __import__("os").path.exists("id_1080.txt"):
    r = c.post(f"{B}/generateVideo", json={"model": "bytedance/seedance-2.5/draft-complete", "draft_id": "757296b6ffb64930a13b4f51ebec2661"}, headers=H)
    r.raise_for_status(); pid = r.json()["data"]["id"]; open("id_1080.txt", "w").write(pid); print("id", pid, flush=True)
pid = open("id_1080.txt").read().strip()
t = time.time()
while time.time() - t < 900:
    d = c.get(f"{B}/prediction/{pid}", headers=H).json()["data"]
    if d["status"] in ("completed", "succeeded", "failed", "error"): break
    time.sleep(10)
print(d["status"], d.get("error"), d.get("price")); json.dump(d, open("res_1080.json", "w"))
