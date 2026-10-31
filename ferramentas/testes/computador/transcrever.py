import base64, json, os, sys, time, urllib.request, urllib.error
K = open(os.path.expanduser("~/.gk")).read().strip()
U = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
for w in sys.argv[1:]:
    for t in range(4):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(U, json.dumps({"contents": [{"parts": [{"text": "Transcreva EXATAMENTE o que é falado, palavra por palavra, sem corrigir. Só a transcrição."},
                {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(open(w, "rb").read()).decode()}}]}]}).encode(), {"x-goog-api-key": K, "Content-Type": "application/json"}), timeout=90)); break
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(15); continue
            raise
    print(w, "|", r["candidates"][0]["content"]["parts"][0]["text"].strip())
