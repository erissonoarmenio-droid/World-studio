import cv2, glob, sys, numpy as np
H="/root/.cache/huggingface/hub/"
det=cv2.FaceDetectorYN.create(glob.glob(H+"models--opencv--face_detection_yunet/snapshots/*/*.onnx")[0],"",(320,320),0.7)
rec=cv2.FaceRecognizerSF.create(glob.glob(H+"models--opencv--face_recognition_sface/snapshots/*/*.onnx")[0],"")
for mp4 in sys.argv[1:]:
    cap=cv2.VideoCapture(mp4); E=[]; F=[]
    while True:
        ok,fr=cap.read()
        if not ok: break
        h,w=fr.shape[:2]; det.setInputSize((w,h)); _,f=det.detect(fr)
        if f is None: E.append(None); F.append(None); continue
        f=max(f,key=lambda x:x[2]*x[3]); E.append(rec.feature(rec.alignCrop(fr,f))); F.append(f)
    e0=next(e for e in E if e is not None)
    linha=[]; salto=[]
    for i in range(0,len(E),12):
        linha.append(f"{i/24:.1f}s:{rec.match(e0,E[i],0):.2f}/w{int(F[i][2])}" if E[i] is not None else f"{i/24:.1f}s:-")
    for i in range(1,len(E)):
        if E[i] is not None and E[i-1] is not None:
            salto.append(rec.match(E[i-1],E[i],0))
    s=np.array(salto); print(mp4, "quadro-a-quadro min", round(s.min(),2), "quadros<0.8:", int((s<0.8).sum()), "em", [round(k/24,2) for k in np.where(s<0.8)[0][:8]]); print("  ", " ".join(linha))
