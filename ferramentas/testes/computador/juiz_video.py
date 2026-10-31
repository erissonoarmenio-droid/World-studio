# Juiz dos vídeos: Gemini assiste o clipe + referência. Uso: python3 juiz_video.py ref.jpg "fala esperada" clip.mp4 [...pares fala clip]
import base64, json, os, sys, time, re, difflib, urllib.request, urllib.error
K = open(os.path.expanduser("~/.gk")).read().strip()
U = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
P = ("Imagem 1 = referência da pessoa. O vídeo é um clipe UGC de loja gerado por IA. Assista com atenção, quadro a quadro, e seja rigoroso. "
     "Fala esperada: \"{fala}\". Responda SÓ JSON: {{\"transcricao\": \"o que ela fala, palavra por palavra\", "
     "\"sincronia_boca\": 0-10, \"mesma_pessoa_do_inicio_ao_fim\": 0-10, \"parecida_com_referencia\": 0-10, \"idade_aparente\": n, "
     "\"maos_ok\": true/false, \"camisa_igual_o_tempo_todo\": true/false, \"espelho_ok\": true/false/null, "
     "\"texto_ou_logo\": true/false, \"celular_visivel_indevido\": true/false, \"musica\": true/false, "
     "\"parece_video_real\": 0-10, \"defeitos\": [\"segundo X: ...\"]}}")
def norm(s): return re.sub(r"[^a-zà-ú ]", " ", s.lower()).split()
ref = sys.argv[1]; args = sys.argv[2:]; out = []
for fala, clip in zip(args[::2], args[1::2]):
    body = {"contents": [{"parts": [{"text": P.format(fala=fala)},
            {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(open(ref, "rb").read()).decode()}},
            {"inlineData": {"mimeType": "video/mp4", "data": base64.b64encode(open(clip, "rb").read()).decode()}}]}],
            "generationConfig": {"responseMimeType": "application/json"}}
    for t in range(4):
        try: r = json.load(urllib.request.urlopen(urllib.request.Request(U, json.dumps(body).encode(), {"x-goog-api-key": K, "Content-Type": "application/json"}), timeout=150)); break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503): time.sleep(15 * (t + 1)); continue
            raise
    j = json.loads(r["candidates"][0]["content"]["parts"][0]["text"])
    j["clip"] = os.path.basename(clip); j["palavras_certas"] = round(difflib.SequenceMatcher(None, norm(fala), norm(j.get("transcricao", ""))).ratio(), 2)
    out.append(j); print(json.dumps(j, ensure_ascii=False))
json.dump(out, open("juiz_video_%d.json" % int(time.time()), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
