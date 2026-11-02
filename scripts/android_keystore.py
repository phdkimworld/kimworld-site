#!/usr/bin/env python3
"""애드핏 전달 앱의 고정 서명 열쇠를 운영자 비밀값 하나(ADFIT_SIGN_SEED)에서 '매번 똑같이' 만들어 낸다.

왜: 디버그 서명은 빌드마다 바뀌어 새 버전을 낼 때마다 운영자가 앱을 지우고 다시 깔아야 했다(2026-11-01).
열쇠 파일을 어디에 보관하지 않고, 운영자가 GitHub 비밀값에 넣은 문자열에서 RSA 열쇠와 인증서를 결정적으로 만든다.
같은 비밀값이면 같은 열쇠·같은 인증서(RSA PKCS#1 v1.5 서명은 결정적, 날짜·일련번호 고정) → 덮어 설치가 된다.

사용: ADFIT_SIGN_SEED=... python3 scripts/android_keystore.py <출력.p12>
출력: PKCS#12 파일(별칭 adfit). 비밀번호는 표준 출력으로 내보내지 않고 같은 이름 + '.pass' 파일에 쓴다.
비밀값·열쇠·비밀번호는 절대 출력하지 않는다.
"""
import hashlib
import hmac
import os
import sys
import datetime as dt

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID


class Drbg:
    """HMAC-SHA256 기반 결정적 난수(씨앗이 같으면 같은 수열)."""
    def __init__(self, seed: bytes):
        self.k, self.v = b"\0" * 32, b"\1" * 32
        self._upd(seed)

    def _upd(self, data: bytes = b""):
        self.k = hmac.new(self.k, self.v + b"\0" + data, hashlib.sha256).digest()
        self.v = hmac.new(self.k, self.v, hashlib.sha256).digest()
        if data:
            self.k = hmac.new(self.k, self.v + b"\1" + data, hashlib.sha256).digest()
            self.v = hmac.new(self.k, self.v, hashlib.sha256).digest()

    def bytes(self, n: int) -> bytes:
        out = b""
        while len(out) < n:
            self.v = hmac.new(self.k, self.v, hashlib.sha256).digest()
            out += self.v
        self._upd()
        return out[:n]


SMALL = [p for p in range(3, 2000, 2) if all(p % q for q in range(3, int(p ** 0.5) + 1, 2))]


def probable_prime(n: int, rnd: Drbg) -> bool:
    if any(n % p == 0 for p in SMALL):
        return n in SMALL
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2; s += 1
    for _ in range(40):
        a = 2 + int.from_bytes(rnd.bytes(len(n.to_bytes((n.bit_length() + 7) // 8, "big"))), "big") % (n - 3)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def prime(bits: int, e: int, rnd: Drbg) -> int:
    while True:
        c = int.from_bytes(rnd.bytes(bits // 8), "big") | (3 << (bits - 2)) | 1
        if (c - 1) % e and probable_prime(c, rnd):
            return c


def derive(seed: str):
    rnd = Drbg(hashlib.sha256(b"kimworld-adfit-sign-v1|" + seed.encode()).digest())
    e = 65537
    while True:
        p, q = prime(1024, e, rnd), prime(1024, e, rnd)
        if p != q:
            break
    if p < q:
        p, q = q, p
    n, phi = p * q, (p - 1) * (q - 1)
    d = pow(e, -1, phi)
    key = rsa.RSAPrivateNumbers(p, q, d, d % (p - 1), d % (q - 1), pow(q, -1, p), rsa.RSAPublicNumbers(e, n)).private_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "drkimworld adfit")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(int.from_bytes(hashlib.sha256(n.to_bytes(256, "big")).digest()[:16], "big") >> 1)
            .not_valid_before(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))
            .not_valid_after(dt.datetime(2076, 1, 1, tzinfo=dt.timezone.utc))
            .sign(key, hashes.SHA256()))
    pw = hashlib.sha256(b"kimworld-adfit-pass|" + seed.encode()).hexdigest()[:32]
    return key, cert, pw


def main() -> int:
    seed = os.environ.get("ADFIT_SIGN_SEED", "")
    if len(seed) < 16:
        print("ADFIT_SIGN_SEED 가 없거나 너무 짧음(16자 이상) — 디버그 서명으로 빌드")
        return 3
    out = sys.argv[1]
    key, cert, pw = derive(seed)
    blob = pkcs12.serialize_key_and_certificates(b"adfit", key, cert, None, serialization.BestAvailableEncryption(pw.encode()))
    with open(out, "wb") as f:
        f.write(blob)
    with open(out + ".pass", "w") as f:
        f.write(pw)
    # 인증서 지문 앞부분만(운영자가 '같은 열쇠인지' 비교하는 용도. 비밀 아님)
    print("인증서 SHA-256 앞 16자:", cert.fingerprint(hashes.SHA256()).hex()[:16])
    return 0


if __name__ == "__main__":
    sys.exit(main())
