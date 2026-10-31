"""Cenas 2–5 no padrão E22: ação em silêncio, fala parada do peito para cima. 2.0 fast 720p."""
import json
V2 = json.load(open("/home/claude/world-studio/tests/geracao/casos/video_v2_2910.json"))["casos"]
LUZ = "UGC style story, filmed on smartphone, warm boutique ceiling light"
CENAS = {
 "c2": dict(duracao=7, audio_segundos=4.1,
   objetivo="Create a talking clip from @image1.",
   formato=f"7 seconds {LUZ}, phone propped on a shelf facing her, framing from the chest up, her face large in the frame.",
   cenario=V2["c2"]["cenario"],
   batidas=("The video opens silent: she raises both open hands beside her face, palms to the camera, and wiggles her "
            "fingers once. Then she holds her hands still beside her face, looks straight into the lens and says in "
            "Brazilian Portuguese: {fala} Final shot — silent, she laughs softly and holds the pose for the final second."),
   tom="The tone is amused, relaxed, warm — natural pause after the sentence; the propped phone wobbles slightly.",
   vibe=V2["c2"]["vibe"]),
 "c3": dict(duracao=9, audio_segundos=6.1,
   objetivo="Create a talking mirror clip from @image1.",
   formato=(f"9 seconds {LUZ}, phone propped facing her and one single tall standing mirror; turn shown full body, "
            "then framing from the chest up while she speaks."),
   cenario=V2["c3"]["cenario"],
   batidas=("The video opens silent, full body: a slow half turn in front of the mirror, the shirt fabric "
            "swings. Jump cut — framing from the chest up, she stands still facing the camera, head steady, and says "
            "in Brazilian Portuguese: {fala} Final shot — silent, she smiles and holds the pose for the final second."),
   tom="The tone is light, amused, confident — she speaks unhurried; the propped phone wobbles slightly.",
   vibe=V2["c3"]["vibe"]),
 "c4": dict(duracao=7, audio_segundos=3.9,
   objetivo="Create a talking clip from @image1.",
   formato=(f"7 seconds {LUZ}, handheld phone; the walk is shown waist up, then a jump cut to framing from the chest "
            "up while she speaks, her face large in the frame, slight handheld micro-movement."),
   cenario=V2["c4"]["cenario"],
   batidas=("The video opens silent: she walks slowly along the rack and takes one wooden hanger with a garment. Jump "
            "cut — framing from the chest up, she stands still holding the hanger, faces the camera, head steady, and "
            "says in Brazilian Portuguese: {fala} Final shot — silent, she smiles and holds the pose for the final second."),
   tom="The tone is casual, cheerful, relaxed — she speaks standing still, never rushing.",
   vibe=V2["c4"]["vibe"]),
 "c5": dict(duracao=6, audio_segundos=4.2,
   objetivo="Create a closing talking clip from @image1.",
   formato=f"6 seconds {LUZ}, phone propped facing her, framing from the chest up, her face large in the frame.",
   cenario=V2["c5"]["cenario"],
   batidas=("The video opens with her lightly holding the front of the shirt to show it, standing still, head steady, "
            "and saying in Brazilian Portuguese: {fala} Final shot — silent, she smiles, gives a small wave and holds "
            "the pose for the final second."),
   tom=V2["c5"]["tom"], vibe=V2["c5"]["vibe"]),
}
for c, d in CENAS.items():
    d["fala"] = V2[c]["fala"]; d["peca"] = V2[c]["peca"]

# v4 (E23): a fala começa no início, parada, do peito para cima; a ação (giro, caminhada) vem de
# clipes já pagos (v2, 480p), sem fala, juntados na edição.
CENAS_V4 = {
 "c3": dict(duracao=8, audio_segundos=6.1,
   objetivo="Create a talking mirror clip from @image1.",
   formato=f"8 seconds {LUZ}, phone propped at chest height facing her, framing from the chest up, her face large in the frame.",
   cenario="The boutique behind her: one single tall standing mirror showing her back, a linen curtain, a clothing rack.",
   batidas=("The video opens with her standing still, facing the camera, head steady, and she says in Brazilian "
            "Portuguese: {fala} Final shot — silent, she smiles and holds the pose for the final second."),
   tom="The tone is light, amused, confident — she speaks unhurried; the propped phone wobbles slightly.",
   vibe=V2["c3"]["vibe"]),
 "c4": dict(duracao=5, audio_segundos=3.9,
   objetivo="Create a talking clip from @image1.",
   formato=f"5 seconds {LUZ}, handheld phone at chest height, framing from the chest up, her face large in the frame, slight handheld micro-movement.",
   cenario=V2["c4"]["cenario"],
   batidas=("The video opens with her standing still in the aisle holding the wooden hanger, facing the camera, head "
            "steady, and she says in Brazilian Portuguese: {fala} Final shot — silent, she smiles and holds the pose "
            "for the final second."),
   tom="The tone is casual, cheerful, relaxed — she speaks standing still, never rushing.",
   vibe=V2["c4"]["vibe"]),
}
for c, d in CENAS_V4.items():
    d["fala"] = V2[c]["fala"]; d["peca"] = V2[c]["peca"]
