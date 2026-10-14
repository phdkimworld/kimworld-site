# 효과음과 배경 드론을 코드로 합성해 나레이션에 섞는다 (외부 음원 없음 → 저작권 문제 없음)
# make_slide_video.py가 불러 쓴다. 단독 실행: python3 sfx.py 출력폴더  → 효과음 견본 wav 저장
import numpy as np, wave, os, sys
SR = 44100
rng = np.random.default_rng(7)

def _t(sec): return np.arange(int(SR * sec)) / SR
def _env(n, a, d):  # 선형 상승 a초, 지수 감쇠 d초
    t = np.arange(n) / SR; e = np.minimum(t / max(a, 1e-4), 1.0)
    return e * np.exp(-np.maximum(t - a, 0) / d)
def _lp(x, k):  # 이동평균 저역 통과
    if k <= 1: return x
    return np.convolve(x, np.ones(k) / k, mode='same')
def _st(x, pan=0.0):  # 모노 → 스테레오 (pan -1..1)
    l, r = np.sqrt((1 - pan) / 2), np.sqrt((1 + pan) / 2)
    return np.stack([x * l * 1.414, x * r * 1.414], 1)

def boom(sec=1.6):  # 긴장감 있는 저음 충격음: 훅·반전·답 공개
    t = _t(sec); f = 38 + 70 * np.exp(-t * 7)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.004, 0.55)
    thump = _lp(rng.standard_normal(len(t)), 40) * _env(len(t), 0.002, 0.06) * 3
    tail = _lp(rng.standard_normal(len(t)), 120) * _env(len(t), 0.02, 0.5) * 2
    x = body + thump + tail; return _st(x / np.abs(x).max())

def whoosh(sec=0.55):  # 화면 전환: 걸러진 잡음이 부풀었다 사라짐, 좌→우
    n = int(SR * sec); t = np.arange(n) / n
    noise = rng.standard_normal(n); x = _lp(noise, 6) - _lp(noise, 60)  # 대역 통과 느낌
    env = np.sin(np.pi * t) ** 2.2; x = x * env; x /= np.abs(x).max()
    pan = np.linspace(-0.7, 0.7, n)
    return np.stack([x * np.sqrt((1 - pan) / 2) * 1.414, x * np.sqrt((1 + pan) / 2) * 1.414], 1)

def riser(sec=2.2):  # 질문 직전 긴장 상승음
    t = _t(sec); f = 180 + 520 * (t / sec) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.5
    noise = _lp(rng.standard_normal(len(t)), 8) * 0.6
    x = (tone + noise) * (t / sec) ** 2.5; x[-int(SR * 0.04):] *= np.linspace(1, 0, int(SR * 0.04))
    return _st(x / np.abs(x).max())

def chime(sec=1.8):  # 사이트 안내(미드롤) 시작: 맑은 두 음 종소리
    t = _t(sec); x = np.zeros(len(t))
    for f0, dl, a in [(1318.5, 0.0, 1.0), (1975.5, 0.12, 0.8)]:
        k = int(SR * dl); tt = t[:len(t) - k]
        tone = (np.sin(2 * np.pi * f0 * tt) + 0.35 * np.sin(2 * np.pi * f0 * 2.76 * tt) * np.exp(-tt * 6)) * np.exp(-tt * 2.6) * a
        x[k:] += tone * np.minimum(tt / 0.003, 1)
    return _st(x / np.abs(x).max())

def tick(sec=0.08):  # 숫자 카드가 뜰 때 짧은 딸깍
    t = _t(sec); x = np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 90) + _lp(rng.standard_normal(len(t)), 3) * np.exp(-t * 200) * 0.4
    return _st(x / np.abs(x).max())

def bed(dur):  # 미스터리 배경 드론: 단조 화음 + 느린 일렁임, 처음·끝 페이드
    n = int(SR * dur); t = np.arange(n) / SR; x = np.zeros(n)
    for f0, a in [(55.0, 1.0), (110.0, 0.7), (130.81, 0.45), (164.81, 0.4), (220.0, 0.18)]:
        for det in (-0.25, 0.25):
            x += a * np.sin(2 * np.pi * (f0 + det) * t + rng.uniform(0, 6.28))
    x *= 0.75 + 0.25 * np.sin(2 * np.pi * t / 9.0)
    air = _lp(rng.standard_normal(n), 400) * 25 * (0.6 + 0.4 * np.sin(2 * np.pi * t / 13.0 + 1))
    x = x / np.abs(x).max() + air * 0.15
    fade = np.minimum(1, np.minimum(t / 3.0, (dur - t) / 4.0)).clip(0)
    x = x * fade / np.abs(x).max()
    l = x; r = np.roll(x, int(SR * 0.013))
    return np.stack([l, r], 1)

GAIN = {'boom': 0.32, 'whoosh': 0.16, 'riser': 0.22, 'chime': 0.20, 'tick': 0.10}
GEN = {'boom': boom, 'whoosh': whoosh, 'riser': riser, 'chime': chime, 'tick': tick}
BED_GAIN = 0.075

def read_wav(p):
    with wave.open(p) as w:
        assert w.getsampwidth() == 2 and w.getframerate() == SR
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        return a.reshape(-1, w.getnchannels()) if w.getnchannels() == 2 else np.stack([a, a], 1)

def write_wav(p, a):
    a = np.clip(a, -1, 1); b = (a * 32767).astype(np.int16)
    with wave.open(p, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(b.tobytes())

def mix(voice_wav, events, out_wav, bed_on=True, bed_db=None):
    """voice_wav(44.1k 스테레오 16bit)에 events=[(시각, 종류)]의 효과음과 배경 드론을 섞는다.
    효과음은 그 순간 나레이션 크기에 맞춰 살짝 줄인다(목소리 가림 방지)."""
    v = read_wav(voice_wav); n = len(v); out = v.copy()
    env = _lp(np.abs(v).mean(1), int(SR * 0.05))  # 나레이션 크기
    if bed_on:
        b = bed(n / SR) * BED_GAIN
        if len(b) < n: b = np.concatenate([b, np.zeros((n - len(b), 2))])  # 반올림으로 한 샘플 짧아지는 경우
        b = b[:n]
        if bed_db is not None:  # 배경음을 나레이션 RMS보다 bed_db dB 낮게(쇼츠 지침: -18~-20dB)
            vr = np.sqrt(np.mean(v[env > 0.02] ** 2)) if (env > 0.02).any() else 0.1
            br = np.sqrt(np.mean(b ** 2)) or 1
            b = b * (vr * 10 ** (bed_db / 20) / br)
        duck = 1 - 0.45 * np.clip(env / 0.12, 0, 1)  # 말할 때 배경을 낮춘다
        out += b * _lp(duck, int(SR * 0.3))[:, None]
    cache = {}
    for t0, kind in events:
        if kind not in GEN: continue
        s = cache.setdefault(kind, GEN[kind]()) * GAIN[kind]
        i = int(t0 * SR)
        if kind == 'riser': i -= len(s)  # 상승음은 그 시각에 끝나도록
        i = max(i, 0); j = min(i + len(s), n)
        if j <= i: continue
        g = 1 - 0.35 * np.clip(env[i:j] / 0.15, 0, 1)
        out[i:j] += s[:j - i] * g[:, None]
    pk = np.abs(out).max()
    if pk > 0.97: out *= 0.97 / pk
    write_wav(out_wav, out)

if __name__ == '__main__':
    d = sys.argv[1] if len(sys.argv) > 1 else '.'; os.makedirs(d, exist_ok=True)
    for k, f in GEN.items(): write_wav(os.path.join(d, f'sfx_{k}.wav'), f() * GAIN[k] * 2)
    write_wav(os.path.join(d, 'sfx_bed.wav'), bed(20) * BED_GAIN * 4)
    print('saved', d)
