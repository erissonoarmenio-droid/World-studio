import base64, json, os, urllib.request
K = open(os.path.expanduser("~/.gk")).read().strip()
p = ("Image 1 shows a woman wearing a light orange linen short-sleeve button-up shirt. Create a clean e-commerce product photo of ONLY that exact shirt, "
     "laid flat (flat lay) on a plain light grey background, front view, fully visible, buttoned, sleeves spread. Keep the exact color, linen texture, "
     "pointed collar, tone-on-tone buttons, short sleeve length and fit. No person, no hanger, no text, no logos, no props. Soft even studio light.")
img = {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(open("c5.png", "rb").read()).decode()}}
body = {"contents": [{"parts": [{"text": p}, img]}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1", "imageSize": "1K"}}}
r = json.load(urllib.request.urlopen(urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/gemini-nano-banana-2.1:generateContent",
     json.dumps(body).encode(), {"x-goog-api-key": K, "Content-Type": "application/json"}), timeout=170))
for part in r["candidates"][0]["content"]["parts"]:
    if "inlineData" in part: open("peca_camisa.png", "wb").write(base64.b64decode(part["inlineData"]["data"])); print("ok"); break
