# Compara A (receita rodada 3), D (pesquisa: preâmbulo + PERFORMANCE + vírgulas), C (pura). Kore. Conferência automática, até 4 tentativas.
import base64, json, os, re, subprocess, time, difflib, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
K = open(os.path.expanduser("~/.gk")).read().strip()
API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
F = {"c1": "Gente, vou provar pra vocês que eu sou inteligência artificial, olha meu rosto, a pele, o dente.",
     "c2": "As mãos, que a IA sempre errava, cinco dedinhos, ó.",
     "c3": "Olha o reflexo no espelho, o tecido mexendo, e nada derretendo, viu?",
     "c4": "E ó, andando, pegando as coisas, tudo certinho.",
     "c5": "E essa camisa? Essa é de verdade, tá aqui na loja, corre!"}
A = ("PERFIL: moça de 25 anos, dona de uma lojinha de roupa, não é locutora. "
     "CENA: gravando story no celular, perto do microfone, como um áudio pra uma amiga. "
     "DIREÇÃO: coloquial, sorriso na voz sem animação de propaganda, sem subir nem cair o tom no fim da frase, "
     "emendando as palavras, volume baixo. Leia SÓ a fala abaixo, nada desta instrução.\nFALA: {}")
D = ("Synthesize speech for the performance defined below. The profile, scene and performance notes are direction only. "
     "Do NOT speak them. Speak ONLY the lines under #### TRANSCRIPT.\n\n"
     "# AUDIO PROFILE: Ju\n## Moça de 25 anos, dona de uma lojinha de roupa no Brasil. Não é locutora, nunca fez propaganda.\n\n"
     "## SCENE\nFim de tarde na loja vazia. Ela segura o celular perto do rosto e grava um story rapidinho, "
     "meio rindo, como se mandasse um áudio pra melhor amiga.\n\n"
     "### PERFORMANCE\nStyle: dá pra ouvir o sorriso, mas sem empolgação de vendedora; jeito de conversa, meio despreocupado.\n"
     "Pace: fala corrida, emendando as palavras, sem pausas longas; o tom não cai no fim das frases.\n"
     "Voice: perto do microfone, volume baixo, português do Brasil bem coloquial.\n\n#### TRANSCRIPT\n{}")
C = "{}"
FMT = {"A": A, "D": D, "C": C}
def call(model, body):
    for t in range(5):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(API.format(model), json.dumps(body).encode(), {"x-goog-api-key": K, "Content-Type": "application/json"}), timeout=90))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503): time.sleep(12 * (t + 1)); continue
            return {"erro": e.code}
def norm(s): return re.sub(r"[^a-zà-ú ]", " ", s.lower()).split()
def um(args):
    f, c = args; log = []
    for tent in range(1, 5):
        r = call("gemini-3.8-flash-tts", {"contents": [{"parts": [{"text": FMT[f].format(F[c])}]}],
                 "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}}}})
        try: pcm = base64.b64decode(r["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
        except Exception: log.append("sem áudio"); continue
        razao = (len(pcm) / 48000) / (len(F[c]) / 14)
        if razao > 1.8: log.append(f"leu instrução ({razao:.1f}x)"); continue
        wav = f"comp_{f}_{c}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0", wav], input=pcm, check=True)
        j = call("gemini-3.8-flash", {"contents": [{"parts": [{"text": "Transcreva EXATAMENTE o que é falado, palavra por palavra. Só a transcrição."},
                 {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(open(wav, "rb").read()).decode()}}]}]})
        try: tr = j["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception: tr = "?"
        sim = difflib.SequenceMatcher(None, norm(F[c]), norm(tr)).ratio()
        if sim < 0.9: log.append(f"palavras {sim:.2f}"); continue
        return {"fmt": f, "cena": c, "ok": True, "tentativas": tent, "falhas": log, "dur": round(len(pcm) / 48000, 1), "sim": round(sim, 2)}
    return {"fmt": f, "cena": c, "ok": False, "tentativas": 4, "falhas": log}
jobs = [(f, c) for f in ("A", "D") for c in F]
with ThreadPoolExecutor(3) as ex: res = list(ex.map(um, jobs))
json.dump(res, open("voz_comp.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for x in res: print(x)
