"""RSA 加密 & gzip 解压工具"""
import base64
import gzip
import io
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# CCTRCloud 公钥（来自 config.js）
_PUB_KEY_B64 = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDDLyh5Lb/5TprGvS9yFCcpCYnb0"
    "FuSyY3+TPbJI7Pv3+u4eFoqGGN46qyFOVLhUuFRttMfoA8h8yrdYCssLi93baoByT"
    "MYf5/KVlviLKXWd3TDOJdeSX4d+qLUp/WK0ckm2VaJuY5vW0x5x6WbZ8MSxwTDMqN"
    "NMgVUdOgD3MIScwIDAQAB"
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
