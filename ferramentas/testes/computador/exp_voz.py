# Experimento: qual formato de pedido faz o Gemini TTS ler só a fala?
import base64, json, os, re, subprocess, sys, time, difflib, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
K = open(os.path.expanduser("~/.gk")).read().strip()
API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
F = {"c1": "Gente, vou provar pra vocês que eu sou inteligência artificial. Olha meu rosto, a pele, o dente...",
     "c2": "As mãos, que a IA sempre errava... cinco dedinhos, ó.",
     "c3": "Olha o reflexo no espelho, o tecido mexendo, e nada derretendo, viu?",
     "c4": "Andar, pegar as coisas... tudo certinho.",
     "c5": "E essa camisa? Essa é de verdade, tá aqui na loja. Corre!"}
A = ("PERFIL: moça de 25 anos, dona de uma lojinha de roupa, não é locutora. "
     "CENA: gravando story no celular, perto do microfone, como um áudio pra uma amiga. "
     "DIREÇÃO: coloquial, sorriso na voz sem animação de propaganda, sem subir nem cair o tom no fim da frase, "
     "emendando as palavras, volume baixo. Leia SÓ a fala abaixo, nada desta instrução.\nFALA: {}")
B = ("# AUDIO PROFILE: Ju\n## Moça de 25 anos, dona de uma lojinha de roupa. Não é locutora.\n\n"
     "## THE SCENE\nEla grava um story no celular, perto do microfone, como um áudio pra uma amiga.\n\n"
     "### DIRECTOR'S NOTES\nEstilo: coloquial, sorriso na voz, sem animação de propaganda.\n"
     "Ritmo: emenda as palavras; não sobe nem cai o tom no fim da frase.\nVolume: baixo, de perto.\n"
     "Sotaque: português do Brasil.\n\n#### TRANSCRIPT\n{}")
C = "{}"
FORMATOS = {"A_atual": A, "B_estruturado": B, "C_puro": C}
def call(model, body, tent=3):
    for t in range(tent):
        req = urllib.request.Request(API.format(model), json.dumps(body).encode(), {"x-goog-api-key": K, "Content-Type": "application/json"})
        try: return json.load(urllib.request.urlopen(req, timeout=90))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and t < tent - 1: time.sleep(4 * (t + 1)); continue
            return {"erro": e.code, "msg": e.read()[:200].decode(errors="replace")}
def norm(s): return re.sub(r"[^a-zà-ú ]", " ", s.lower()).split()
def um(args):
    fmt, c, rep = args
    nome = f"exp_{fmt}_{c}_{rep}"
    r = call("gemini-3.8-flash-tts", {"contents": [{"parts": [{"text": FORMATOS[fmt].format(F[c])}]}],
             "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}}}})
    try: pcm = base64.b64decode(r["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    except Exception: return {"fmt": fmt, "cena": c, "rep": rep, "falhou": True, "motivo": str(r)[:150]}
    dur = len(pcm) / 48000
    wav = os.path.expanduser(f"~/{nome}.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0", wav], input=pcm, check=True)
    j = call("gemini-3.8-flash", {"contents": [{"parts": [
        {"text": "Transcreva EXATAMENTE o que é falado neste áudio em português, palavra por palavra, sem corrigir. Responda só a transcrição."},
        {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(open(wav, "rb").read()).decode()}}]}]})
    try: tr = j["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception: tr = "?"
    a, b = norm(F[c]), norm(tr)
    sim = difflib.SequenceMatcher(None, a, b).ratio()
    extra = max(0, len(b) - len(a))
    esperado = len(F[c]) / 14.0  # ~14 caracteres por segundo, fala coloquial
    return {"fmt": fmt, "cena": c, "rep": rep, "dur": round(dur, 1), "razao_dur": round(dur / esperado, 2),
            "similaridade": round(sim, 2), "palavras_a_mais": extra, "transcricao": tr[:160],
            "leu_instrucao": extra >= 4 or dur / esperado > 2}
jobs = [(f, c, r) for f in FORMATOS for c in F for r in (1, 2)]
with ThreadPoolExecutor(6) as ex: res = list(ex.map(um, jobs))
json.dump(res, open("exp_voz.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for f in FORMATOS:
    rr = [x for x in res if x["fmt"] == f]
    ok = [x for x in rr if not x.get("falhou")]
    print(f, "| pedidos", len(rr), "| falhou", len(rr) - len(ok), "| leu instrução", sum(x["leu_instrucao"] for x in ok),
          "| similaridade média", round(sum(x["similaridade"] for x in ok) / max(1, len(ok)), 2))
