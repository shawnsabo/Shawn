"""RSA 加密 & gzip 解压工具"""
import base64
import gzip
import io
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# CCTRCloud 公钥（www.cctrcloud.net/practice/js/config.js，2026-11 实测现行版本；
# 旧公钥已被平台弃用）
_PUB_KEY_B64 = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDO3r40irpueBqKoCSh01YG8qhX"
    "XH10pgZje98q7ZvjOWad/da8Eejrbs3uyNOEwYmFJckUA8X0MiGOr3Mlv1VAXTA9"
    "T9YxbBObkLNUMj2VWLbjgZNiDzZwqeprLVvIbQSLSEUseVf/EmdCeEgMOzxnahsK"
    "KIs7u+iN13xPFBY0kwIDAQAB"
)

_cipher = PKCS1_v1_5.new(RSA.import_key(base64.b64decode(_PUB_KEY_B64)))


def rsa_encrypt(text: str) -> str:
    """RSA 加密密码"""
    encrypted = _cipher.encrypt(text.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def decompress_gzip_base64(raw: bytes | str) -> bytes:
    """解压 base64(gzip(data))，返回原始字节"""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    compressed = base64.b64decode(raw)
    return gzip.decompress(compressed)
