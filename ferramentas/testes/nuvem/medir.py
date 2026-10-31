"""Mede por quadro: identidade (SFace vs referência), tremor do rosto e sincronia boca×áudio."""
import cv2, json, sys, subprocess, wave, numpy as np, glob
import mediapipe as mp
from mediapipe.tasks.python import vision, BaseOptions
H = "/root/.cache/huggingface/hub/"
det = cv2.FaceDetectorYN.create(glob.glob(H+"models--opencv--face_detection_yunet/snapshots/*/face_detection_yunet_2023mar.onnx")[0], "", (320, 320), 0.7)
rec = cv2.FaceRecognizerSF.create(glob.glob(H+"models--opencv--face_recognition_sface/snapshots/*/face_recognition_sface_2021dec.onnx")[0], "")
lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path="face_landmarker.task"), num_faces=2))
def emb(img):
    h, w = img.shape[:2]; det.setInputSize((w, h)); _, f = det.detect(img)
    if f is None: return None, None
    f = max(f, key=lambda x: x[2]*x[3])  # maior rosto (o real, não o reflexo)
    return rec.feature(rec.alignCrop(img, f)), f
ref = cv2.imread("/mnt/user-data/uploads/TESTE INFLUENCER/trabalho/influencer.jpg"); eref, _ = emb(ref)
def audio_env(mp4, fps):
    subprocess.run(["ffmpeg","-y","-loglevel","error","-i",mp4,"-vn","-ac","1","-ar","16000","/tmp/a.wav"],check=True)
    w = wave.open("/tmp/a.wav"); a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
    n = int(16000/fps); return np.array([np.sqrt(np.mean(a[i*n:(i+1)*n]**2)+1e-9) for i in range(len(a)//n)])
res = {}
for mp4 in sys.argv[1:]:
    cap = cv2.VideoCapture(mp4); fps = cap.get(cv2.CAP_PROP_FPS); sims=[]; boca=[]; caixa=[]; i=0
    while True:
        ok, fr = cap.read()
        if not ok: break
        e, f = emb(fr)
        sims.append(float(rec.match(eref, e, cv2.FaceRecognizerSF_FR_COSINE)) if e is not None else np.nan)
        caixa.append(f[:4].tolist() if f is not None else None)
        r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)))
        if r.face_landmarks:
            L = max(r.face_landmarks, key=lambda l: abs(l[234].x-l[454].x))
            boca.append(abs(L[13].y-L[14].y)/max(abs(L[10].y-L[152].y),1e-6))
        else: boca.append(np.nan)
        i += 1
    s = np.array(sims); b = np.array(boca); env = audio_env(mp4, fps)[:len(b)]; b = b[:len(env)]
    ok = ~np.isnan(b)
    corr = float(np.corrcoef(b[ok], env[ok])[0,1]) if ok.sum()>10 else None
    # melhor atraso (boca atrasada/adiantada até 0,3 s)
    best = max(((float(np.corrcoef(np.roll(b,k)[ok], env[ok])[0,1]), k) for k in range(-7,8)), default=(None,0))
    d = np.abs(np.diff(s[~np.isnan(s)]))
    res[mp4] = {"qps": round(fps,1), "quadros": i, "id_media": round(float(np.nanmean(s)),3), "id_min": round(float(np.nanmin(s)),3),
                "id_quedas>0.15": int((d>0.15).sum()), "id_pior_quadro_s": round(float(np.nanargmin(s))/fps,2),
                "sem_rosto": int(np.isnan(s).sum()), "boca_x_audio": None if corr is None else round(corr,2),
                "boca_x_audio_melhor_atraso": [round(best[0],2), round(best[1]/fps,2)]}
    print(mp4, json.dumps(res[mp4]), flush=True)
json.dump(res, open("medidas.json","w"), indent=1)
