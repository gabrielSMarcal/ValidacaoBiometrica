"""Segredos fora do banco; AES-GCM autentica conteúdo e vínculo ao usuário."""
import base64
import hashlib
import hmac
import json
import secrets
import zlib

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class Seguranca:
    def __init__(self, chave_base64: str):
        self._key = base64.b64decode(chave_base64, altchars=b'-_', validate=True)
        self._aes = AESGCM(self._key)
        self._cpf_key = hmac.digest(self._key, b'aps:indice-cpf:v1', 'sha256')
        self.senhas = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
        self.hash_ficticio = self.senhas.hash(secrets.token_urlsafe(32))

    def cifrar(self, valor: dict, usuario_id: str, tipo: str) -> bytes:
        serializado = json.dumps(valor, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        nonce = secrets.token_bytes(12)
        aad = f'aps:v1:{tipo}:{usuario_id}'.encode('utf-8')
        return b'APS1' + nonce + self._aes.encrypt(nonce, zlib.compress(serializado), aad)

    def decifrar(self, blob: bytes, usuario_id: str, tipo: str) -> dict:
        if not isinstance(blob, bytes) or len(blob) < 32 or blob[:4] != b'APS1':
            raise ValueError('Envelope biométrico inválido.')
        aad = f'aps:v1:{tipo}:{usuario_id}'.encode('utf-8')
        comprimido = self._aes.decrypt(blob[4:16], blob[16:], aad)
        # Limite de expansão mesmo quando o ciphertext é autenticado.
        descompactador = zlib.decompressobj()
        bruto = descompactador.decompress(comprimido, 1_000_001)
        if len(bruto) > 1_000_000 or not descompactador.eof or descompactador.unused_data:
            raise ValueError('Assinatura acima do limite ou incompleta.')
        valor = json.loads(bruto)
        if not isinstance(valor, dict):
            raise ValueError('Assinatura inválida.')
        return valor

    def indice_cpf(self, cpf: str) -> str:
        return hmac.new(self._cpf_key, cpf.encode('ascii'), hashlib.sha256).hexdigest()

    def verificar_senha(self, senha: str, senha_hash: str | None) -> bool:
        try:
            return self.senhas.verify(senha_hash or self.hash_ficticio, senha) and senha_hash is not None
        except (VerificationError, InvalidHashError):
            return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()
