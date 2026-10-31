# Falas finais: formato B (estruturado) + conferência automática (transcrição, duração). Refaz no máximo 2x.
import base64, json, os, re, subprocess, time, difflib, urllib.request, urllib.error
K = open(os.path.expanduser("~/.gk")).read().strip()
API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
F = {"c1": "Gente, vou provar pra vocês que eu sou inteligência artificial, olha meu rosto, a pele, o dente.",
     "c2": "As mãos, que a IA sempre errava, cinco dedinhos, ó.",
     "c3": "Olha o reflexo no espelho, o tecido mexendo, e nada derretendo, viu?",
     "c4": "E ó, andando, pegando as coisas, tudo certinho.",
     "c5": "E essa camisa? Essa é de verdade, tá aqui na loja, corre!"}
B = ("# AUDIO PROFILE: Ju\n## Moça de 25 anos, dona de uma lojinha de roupa. Não é locutora.\n\n"
     "## THE SCENE\nEla grava um story no celular, perto do microfone, como um áudio pra uma amiga.\n\n"
     "### DIRECTOR'S NOTES\nEstilo: coloquial, sorriso na voz, sem animação de propaganda.\n"
     "Ritmo: emenda as palavras, sem pausas longas; não sobe nem cai o tom no fim da frase.\nVolume: baixo, de perto.\n"
     "Sotaque: português do Brasil.\n\n#### TRANSCRIPT\n{}")
def call(model, body):
    for t in range(5):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(API.format(model), json.dumps(body).encode(), {"x-goog-api-key": K, "Content-Type": "application/json"}), timeout=90))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503): time.sleep(10 * (t + 1)); continue
            return {"erro": e.code}
def norm(s): return re.sub(r"[^a-zà-ú ]", " ", s.lower()).split()
rel = []
for c, fala in F.items():
    for tent in range(1, 4):
        r = call("gemini-3.8-flash-tts", {"contents": [{"parts": [{"text": B.format(fala)}]}],
                 "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}}}})
        try: pcm = base64.b64decode(r["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
        except Exception: rel.append({"cena": c, "tent": tent, "ok": False, "motivo": "sem áudio"}); continue
        wav = f"final_{c}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0", wav], input=pcm, check=True)
        dur = len(pcm) / 48000; razao = dur / (len(fala) / 14)
        j = call("gemini-3.8-flash", {"contents": [{"parts": [{"text": "Transcreva EXATAMENTE o que é falado, palavra por palavra. Só a transcrição."},
                 {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(open(wav, "rb").read()).decode()}}]}]})
        try: tr = j["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception: tr = "?"
        sim = difflib.SequenceMatcher(None, norm(fala), norm(tr)).ratio()
        ok = sim >= 0.9 and razao <= 1.8
        rel.append({"cena": c, "tent": tent, "dur": round(dur, 1), "razao": round(razao, 2), "sim": round(sim, 2), "ok": ok, "transcricao": tr})
        if ok: break
json.dump(rel, open("voz_final.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for x in rel: print(x)
