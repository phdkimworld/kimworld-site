# 슈퍼토닉 남성 TTS: 문단마다 합성해 이어 붙이고, 문단·문장 시각표(<출력>_timing.json)를 함께 저장
# 사용: python3 st_tts.py 나레이션.txt 출력.wav [화자=6] [속도=1.15] [스텝=10]
import sys, subprocess, wave, json, re, os, tempfile
import numpy as np
src, dst = sys.argv[1], sys.argv[2]
sid = sys.argv[3] if len(sys.argv) > 3 else '6'
speed = sys.argv[4] if len(sys.argv) > 4 else '1.15'
steps = sys.argv[5] if len(sys.argv) > 5 else '10'
GAP = 0.6
paras = [p.strip() for p in open(src, encoding='utf-8').read().split('\n') if p.strip()]
split = lambda p: [s for s in re.split(r'(?<=[.?!])\s+', p) if s.strip()]

def gaps_of(a, sr):
    hop = int(sr * 0.01); n = len(a) // hop
    if n == 0: return []
    e = np.sqrt((a[:n * hop].astype(np.float32).reshape(n, hop) ** 2).mean(1))
    th = max(np.percentile(e, 95) * 0.04, 40); sil = e < th; g = []; i = 0
    while i < n:
        if sil[i]:
            j = i
            while j < n and sil[j]: j += 1
            if (j - i) >= 15 and i > 0 and j < n: g.append(((i + j) / 200, (j - i) / 100))
            i = j
        else: i += 1
    return g

def align(sents, a, sr):
    # 문장 경계 = 글자 수 비례 예상 시각에 가장 가까운 긴 무음 구간의 가운데
    dur = len(a) / sr
    if len(sents) == 1: return [0.0, dur]
    w = [len(re.sub(r'\s', '', s)) for s in sents]; tot = sum(w)
    cand = gaps_of(a, sr); bounds = [0.0]; used = -1
    for k in range(1, len(sents)):
        exp = dur * sum(w[:k]) / tot; best = None
        for gi, (mid, ln) in enumerate(cand):
            if gi <= used or mid <= bounds[-1] + 0.5: continue
            score = abs(mid - exp) - min(ln, 0.8) * 1.5
            if best is None or score < best[0]: best = (score, gi, mid)
        if best and abs(best[2] - exp) < max(2.5, dur * 0.25): used = best[1]; bounds.append(best[2])
        else: bounds.append(max(exp, bounds[-1] + 0.5))
    bounds.append(dur); return bounds

sr = None; out = []; t = 0.0; timing = []
tmp = tempfile.mkdtemp()
for i, p in enumerate(paras):
    f = f'{tmp}/p{i}.wav'
    subprocess.run(['/home/claude/tts/st/st.sh', sid, p, f, speed, steps], capture_output=True)
    w = wave.open(f); sr = w.getframerate()
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    sents = split(p); b = align(sents, a, sr)
    timing.append({"start": round(t, 3), "end": round(t + len(a) / sr, 3),
                   "sents": [{"start": round(t + b[k], 3), "end": round(t + b[k + 1], 3), "text": s} for k, s in enumerate(sents)]})
    out += [a, np.zeros(int(sr * GAP), np.int16)]; t += len(a) / sr + GAP
    print(f'para {i+1}/{len(paras)}', flush=True)
with wave.open(dst, 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(np.concatenate(out).tobytes())
json.dump({"duration": round(t, 3), "paras": timing}, open(os.path.splitext(dst)[0] + '_timing.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('done', dst)
