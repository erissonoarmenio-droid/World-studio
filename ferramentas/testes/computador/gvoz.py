# uso: python3 gvoz.py   (gera c1..c5.wav com Kore, gemini-3.8-flash-tts)
import base64, json, os, subprocess, sys, urllib.request, urllib.error
K = open(os.path.expanduser("~/.gk")).read().strip()
D = ("PERFIL: moça de 25 anos, dona de uma lojinha de roupa, não é locutora. "
     "CENA: gravando story no celular, perto do microfone, como um áudio pra uma amiga. "
     "DIREÇÃO: coloquial, sorriso na voz sem animação de propaganda, sem subir nem cair o tom no fim da frase, "
     "emendando as palavras, volume baixo. Leia SÓ a fala abaixo, nada desta instrução.\nFALA: ")
F = {"c1": "Gente, vou provar pra vocês que eu sou inteligência artificial. Olha meu rosto, a pele, o dente...",
     "c2": "As mãos, que a IA sempre errava... cinco dedinhos, ó.",
     "c3": "Olha o reflexo no espelho, o tecido mexendo, e nada derretendo, viu?",
     "c4": "Andar, pegar as coisas... tudo certinho.",
     "c5": "E essa camisa? Essa é de verdade, tá aqui na loja. Corre!"}
for c in (sys.argv[1:] or F):
    body = {"contents": [{"parts": [{"text": D + F[c]}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}}}}
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash-tts:generateContent",
                                 json.dumps(body).encode(), {"x-goog-api-key": K, "Content-Type": "application/json"})
    try: r = json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e: print(c, "erro", e.code, e.read()[:200]); continue
    try: pcm = base64.b64decode(r["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    except Exception: print(c, "sem audio", r.get("candidates", [{}])[0].get("finishReason")); continue
    open(os.path.expanduser(f"~/v_{c}.pcm"), "wb").write(pcm)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", os.path.expanduser(f"~/v_{c}.pcm"), f"v_{c}.wav"], check=True)
    print(c, round(len(pcm) / 48000, 1), "s")
