"""Aplicação principal: configuração, persistência, segurança, modelos e API.

O processamento de imagens permanece explícito nos cinco módulos de fases.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import ssl
import sys
import tempfile
import zlib
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Annotated, Any
from urllib.request import Request as URLRequest, urlopen
from uuid import uuid4

import certifi
import numpy as np
from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import (Boolean, CheckConstraint, Computed, Date, DateTime, ForeignKey, Integer,
                        LargeBinary, String, UniqueConstraint, create_engine, delete, select, text)
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, validates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .processamento.sensoriamento import BiometriaErro, BiometriaIndisponivel, _registrar_diagnostico, sensoriamento
from .processamento.pre_processamento import pre_processamento
from .processamento.segmentacao import (FOCO_MINIMO_EXPERIMENTAL, GUIA, _validar_movimento,
                          segmentacao as _segmentacao)
from .processamento.extracao_caracteristicas import (ALGORITMO, DIMENSAO, _criar_assinatura,
                                       extracao_caracteristicas as _extracao_caracteristicas)
from .processamento.classificacao_interpretacao import (LIMIAR_EXPERIMENTAL,
                                         LIMITE_CONSISTENCIA, MARGEM_EXPERIMENTAL,
                                         classificacao_interpretacao, comparar_assinaturas)


# Configuração e contratos de entrada


class Entrada(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)


class Frame(Entrada):

    largura: Annotated[int, Field(strict=True, ge=160, le=640)]
    altura: Annotated[int, Field(strict=True, ge=120, le=480)]
    rgb_base64: str = Field(min_length=1, max_length=1_228_800)


class Captura(Entrada):

    frames: list[Frame] = Field(min_length=3, max_length=5)


def normalizar_cpf(value: str) -> str:

    if not re.fullmatch(r'[0-9.\- ]{11,18}', value):
        raise ValueError('Informe um CPF válido.')

    cpf = re.sub(r'[^0-9]', '', value)

    if len(cpf) != 11 or len(set(cpf)) == 1:
        raise ValueError('Informe um CPF válido.')

    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[tamanho]):
            raise ValueError('Dígitos verificadores do CPF inválidos.')

    return cpf


class Credenciais(Entrada):

    cpf: str = Field(min_length=11, max_length=18)
    senha: str = Field(min_length=8, max_length=128)
    _cpf = field_validator('cpf')(normalizar_cpf)


class Cadastro(Credenciais, Entrada):

    nome: str = Field(min_length=2, max_length=120)
    nivel: Annotated[int, Field(strict=True, ge=1, le=3)]
    frames: list[Frame] = Field(min_length=5, max_length=5)

    @field_validator('nome')
    @classmethod
    def nome_valido(cls, value: str) -> str:

        value = ' '.join(value.split())

        if len(value) < 2 or any(ord(c) < 32 for c in value):
            raise ValueError('Informe o nome do usuário.')

        return value


class UsuarioAtualizacao(Entrada):

    nome: str | None = Field(default=None, min_length=2, max_length=120)
    nivel: Annotated[int, Field(strict=True, ge=1, le=3)] | None = None
    ativo: bool | None = None
    senha: str | None = Field(default=None, min_length=8, max_length=128)

    _nome = field_validator('nome')(Cadastro.nome_valido.__func__)

    @model_validator(mode='after')

    def possui_alteracao(self):

        if not self.model_fields_set:
            raise ValueError('Informe ao menos um campo para atualizar.')

        return self


ROOT = Path(__file__).resolve().parent.parent


def chave_local() -> SecretStr:
    """Chave persistente por instalação"""
    arquivo = ROOT / '.runtime' / 'biometric.key'
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    try:
        with arquivo.open('x', encoding='utf-8') as destino:
            destino.write(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
    except FileExistsError:
        pass
    return SecretStr(arquivo.read_text(encoding='utf-8').strip())


class Settings(BaseSettings):

    model_config = SettingsConfigDict(env_file=ROOT / '.env', env_file_encoding='utf-8',
                                     extra='ignore', hide_input_in_errors=True)

    db_host: str = '127.0.0.1'
    db_port: int = Field(default=3306, ge=1, le=65535)
    db_name: str = Field(default='aps_facial', min_length=1, max_length=64)
    db_user: str = 'root'
    db_password: SecretStr = SecretStr('')
    admin_cpf: SecretStr | None = Field(default=None, repr=False, exclude=True)
    admin_password_hash: SecretStr | None = Field(default=None, repr=False, exclude=True)
    biometric_key: SecretStr = Field(default_factory=chave_local, validate_default=True)
    allowed_origins: str = ('http://127.0.0.1:4200,http://localhost:4200,'
                            'http://127.0.0.1:5500,http://localhost:5500,'
                            'http://127.0.0.1:8080,http://localhost:8080')
    session_minutes: int = Field(default=15, ge=1, le=120)
    cookie_secure: bool = False
    rate_limit_per_minute: int = Field(default=20, ge=1, le=300)

    @property
    def face_threshold(self) -> float:
        """Política do reconhecimento; valores antigos no .env são ignorados."""
        return LIMIAR_EXPERIMENTAL

    @property
    def face_margin(self) -> float:
        return MARGEM_EXPERIMENTAL

    @field_validator('admin_cpf')
    @classmethod
    def validar_cpf_admin(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        return SecretStr(normalizar_cpf(value.get_secret_value()))

    @field_validator('admin_password_hash')
    @classmethod
    def validar_hash_admin(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        try:
            if extract_parameters(value.get_secret_value()).type != Type.ID:
                raise ValueError
        except (InvalidHashError, ValueError):
            raise ValueError('ADMIN_PASSWORD_HASH deve conter um hash Argon2id válido.') from None
        return value

    @field_validator('biometric_key')

    @classmethod
    def valid_key(cls, value: SecretStr) -> SecretStr:

        try:
            raw = base64.b64decode(value.get_secret_value(), altchars=b'-_', validate=True)
            if len(raw) != 32:
                raise ValueError

        except (ValueError, TypeError) as exc:
            raise ValueError('BIOMETRIC_KEY deve conter 32 bytes em base64. Confira a chave original '
                             'no ambiente, .env ou .runtime/biometric.key.') from exc

        return value

    @property
    def database_url(self) -> URL:
        return URL.create('mysql+pymysql', username=self.db_user,
                          password=self.db_password.get_secret_value(), host=self.db_host,
                          port=self.db_port, database=self.db_name, query={'charset': 'utf8mb4'})

    @property
    def origins(self) -> set[str]:
        return {s.strip().rstrip('/') for s in self.allowed_origins.split(',') if s.strip()}


# Persistência e proteção dos dados


def agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = 'usuarios'
    __table_args__ = (
        CheckConstraint('nivel BETWEEN 1 AND 4', name='ck_usuario_nivel'),
        UniqueConstraint('admin_unico', name='uq_usuario_admin_unico'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    biometria_ref: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()))
    nome: Mapped[str] = mapped_column(String(120))
    cpf_indice: Mapped[str] = mapped_column(String(64), unique=True)
    cpf_cifrado: Mapped[bytes] = mapped_column(LargeBinary)
    senha_hash: Mapped[str] = mapped_column(String(255))
    assinatura_cifrada: Mapped[bytes | None] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB(), 'mysql'), nullable=True)
    nivel: Mapped[int] = mapped_column(Integer)
    admin_unico: Mapped[int | None] = mapped_column(
        Integer, Computed('CASE WHEN nivel = 4 THEN 1 ELSE NULL END', persisted=True))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    @validates('biometria_ref')
    def referencia_imutavel(self, _nome, valor):
        anterior = getattr(self, 'biometria_ref', None)
        if anterior is not None and anterior != valor:
            raise ValueError('A referência criptográfica do usuário é imutável.')
        return valor


class LogAcesso(Base):

    __tablename__ = 'logs_acesso'
    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True)
    evento: Mapped[str] = mapped_column(String(40))
    sucesso: Mapped[bool] = mapped_column(Boolean)
    motivo: Mapped[str] = mapped_column(String(60))
    requisicao_id: Mapped[str] = mapped_column(String(36))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, index=True)


class Sessao(Base):

    __tablename__ = 'sessoes'
    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id', ondelete='CASCADE'), index=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime, index=True)


class DesafioBiometrico(Base):

    __tablename__ = 'desafios_biometricos'
    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id', ondelete='CASCADE'), index=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime, index=True)
    senha_fingerprint: Mapped[str] = mapped_column(String(64))


# Cofre de dossiês: cada nível recebe um recorte próprio (não cumulativo).


class Dossie(Base):

    __tablename__ = 'dossies'
    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    titulo: Mapped[str] = mapped_column(String(160))
    situacao: Mapped[str] = mapped_column(String(60))
    divisao: Mapped[str] = mapped_column(String(120))
    atualizado_em: Mapped[date] = mapped_column(Date)


class DossieRecorte(Base):

    __tablename__ = 'dossie_recortes'
    __table_args__ = (
        CheckConstraint('nivel BETWEEN 1 AND 3', name='ck_recorte_nivel'),
        UniqueConstraint('dossie_id', 'nivel', name='uq_recorte_dossie_nivel'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Sem index=True: o InnoDB indexa a chave estrangeira sem exigir o privilégio INDEX.
    dossie_id: Mapped[int] = mapped_column(ForeignKey('dossies.id', ondelete='CASCADE'))
    nivel: Mapped[int] = mapped_column(Integer)
    resumo: Mapped[str] = mapped_column(String(600))
    orientacao: Mapped[str] = mapped_column(String(400))


TIPOS_REGISTRO = ('campo', 'pendencia', 'decisao', 'historico')
SITUACOES_ABERTAS = ('Aberta', 'Pendente')


class DossieRegistro(Base):

    __tablename__ = 'dossie_registros'
    __table_args__ = (
        CheckConstraint("tipo IN ('campo', 'pendencia', 'decisao', 'historico')", name='ck_registro_tipo'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recorte_id: Mapped[int] = mapped_column(ForeignKey('dossie_recortes.id', ondelete='CASCADE'))
    tipo: Mapped[str] = mapped_column(String(20))
    titulo: Mapped[str] = mapped_column(String(160))
    descricao: Mapped[str | None] = mapped_column(String(600), nullable=True)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)
    situacao: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0)


def criar_engine(settings: Settings):

    return create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=1800,
                         connect_args={'connect_timeout': 5}, hide_parameters=True)


def fabrica_sessoes(engine):

    return sessionmaker(bind=engine, expire_on_commit=False)


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


# Modelos locais: carregamento e inferência


class ModeloFacialIndisponivel(RuntimeError):
    """Os modelos locais ou suas dependências não estão disponíveis."""


@dataclass(frozen=True)
class _Modelo:
    arquivo: str
    url: str
    sha256: str
    tamanho: int


DIRETORIO_MODELOS = ROOT / '.runtime' / 'modelos'
_DETECTOR = _Modelo(
    'face_detection_yunet_2023mar.onnx',
    'https://media.githubusercontent.com/media/opencv/opencv_zoo/'
    '48b10fa505aeb51fbd127fc60a5c660040e823b7/models/'
    'face_detection_yunet/face_detection_yunet_2023mar.onnx',
    '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4',
    232589,
)


_RECONHECEDOR = _Modelo(
    'glintr100.onnx',
    'https://huggingface.co/fal/AuraFace-v1/resolve/'
    'af6d057c9b0ec4071d4c49c80e3539258798b609/glintr100.onnx',
    'a7933ea5330113b01c9b60351d8f4c33003f145d8470ac5f0e52ee2effe25c60',
    260694151,
)


_MODELOS = (_DETECTOR, _RECONHECEDOR)
_PREPARACAO_LOCK = Lock()
_CARGA_LOCK = Lock()
_DETECCAO_LOCK = Lock()


_detector = None


_sessao = None


_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _arquivo_valido(modelo: _Modelo) -> bool:
    caminho = DIRETORIO_MODELOS / modelo.arquivo
    try:
        if not caminho.is_file() or caminho.stat().st_size != modelo.tamanho:
            return False
        checksum = hashlib.sha256()
        with caminho.open('rb') as arquivo:
            for bloco in iter(lambda: arquivo.read(1024 * 1024), b''):
                checksum.update(bloco)
        return checksum.hexdigest() == modelo.sha256
    except OSError:
        return False


def _exigir_arquivo(modelo: _Modelo) -> Path:
    if not _arquivo_valido(modelo):
        raise ModeloFacialIndisponivel(
            'Modelo facial ausente ou inválido. Execute python scripts/preparar_modelos.py '
            'no diretório backend.'
        )
    return DIRETORIO_MODELOS / modelo.arquivo


def _progresso_modelo(modelo: _Modelo, recebidos: int, final: bool = False) -> None:
    percentual = recebidos / modelo.tamanho * 100
    terminal = sys.stdout.isatty()
    mensagem = (f'{modelo.arquivo}: {recebidos / 1_000_000:.2f} MB / '
                f'{modelo.tamanho / 1_000_000:.2f} MB ({percentual:.1f}%)')
    print(('\r' if terminal else '') + mensagem,
          end='\n' if final or not terminal else '', flush=True)


def _baixar_modelo(modelo: _Modelo, mostrar_progresso: bool = False) -> None:
    parcial = None
    progresso_aberto = False
    try:
        DIRETORIO_MODELOS.mkdir(parents=True, exist_ok=True)
        checksum = hashlib.sha256()
        recebidos = 0
        if mostrar_progresso:
            print('O download pode levar alguns minutos, dependendo da conexão. Aguarde.', flush=True)
            _progresso_modelo(modelo, 0)
            progresso_aberto = True
        ultima_atualizacao = monotonic()
        requisicao = URLRequest(modelo.url, headers={'User-Agent': 'APS-Facial/1.0'})
        with tempfile.NamedTemporaryFile(
            mode='wb', prefix=modelo.arquivo + '.', suffix='.part',
            dir=DIRETORIO_MODELOS, delete=False,
        ) as destino:
            parcial = Path(destino.name)
            with urlopen(requisicao, timeout=300, context=_SSL_CONTEXT) as resposta:
                while True:
                    bloco = resposta.read(min(256 * 1024, modelo.tamanho - recebidos + 1))
                    if not bloco:
                        break
                    recebidos += len(bloco)
                    if recebidos > modelo.tamanho:
                        raise ModeloFacialIndisponivel('O modelo recebido ultrapassou o tamanho permitido.')
                    checksum.update(bloco)
                    destino.write(bloco)
                    if mostrar_progresso and recebidos < modelo.tamanho and monotonic() - ultima_atualizacao >= 0.5:
                        _progresso_modelo(modelo, recebidos)
                        ultima_atualizacao = monotonic()
            if mostrar_progresso:
                _progresso_modelo(modelo, recebidos, final=True)
                progresso_aberto = False
                print('Verificando a integridade do arquivo baixado...', flush=True)
            if recebidos != modelo.tamanho or checksum.hexdigest() != modelo.sha256:
                raise ModeloFacialIndisponivel('O modelo recebido falhou na verificação de integridade.')
            destino.flush()
            os.fsync(destino.fileno())
        os.replace(parcial, DIRETORIO_MODELOS / modelo.arquivo)
        parcial = None
        if mostrar_progresso:
            print(f'{modelo.arquivo}: instalado e verificado.', flush=True)
    except ModeloFacialIndisponivel:
        raise
    except Exception as exc:
        if isinstance(exc, OSError):
            detalhe = 'verifique a conexão, o certificado SSL e as permissões da pasta .runtime/modelos'
        else:
            detalhe = 'verifique a integridade do download e as permissões da pasta .runtime/modelos'
        raise ModeloFacialIndisponivel(
            f'Não foi possível preparar o modelo {modelo.arquivo}; {detalhe}.'
        ) from exc
    finally:
        if parcial is not None:
            try:
                parcial.unlink(missing_ok=True)
            except OSError:
                pass
        if progresso_aberto and sys.stdout.isatty():
            print(flush=True)


def preparar_modelos(mostrar_progresso: bool = False) -> None:
    """Baixa somente os artefatos fixados e instala após verificar SHA-256."""
    with _PREPARACAO_LOCK:
        for modelo in _MODELOS:
            if mostrar_progresso:
                print(f'Verificando {modelo.arquivo} ({modelo.tamanho / 1_000_000:.2f} MB)...', flush=True)
            if not _arquivo_valido(modelo):
                _baixar_modelo(modelo, mostrar_progresso=mostrar_progresso)
            elif mostrar_progresso:
                print('Arquivo já disponível e verificado; download dispensado.', flush=True)


def _carregar_detector():
    global _detector
    if _detector is not None:
        return _detector
    with _CARGA_LOCK:
        if _detector is not None:
            return _detector
        caminho = _exigir_arquivo(_DETECTOR)
        try:
            import cv2
            detector = cv2.FaceDetectorYN_create(
                'onnx', np.frombuffer(caminho.read_bytes(), dtype=np.uint8),
                np.empty(0, dtype=np.uint8), (320, 240), 0.90, 0.3, 5000,
            )
            if detector is None:
                raise ValueError
        except Exception:
            raise ModeloFacialIndisponivel(
                'Não foi possível carregar o detector YuNet. Confira os modelos e as dependências do backend.'
            ) from None
        _detector = detector
    return _detector


def _carregar_sessao():
    global _sessao
    if _sessao is not None:
        return _sessao
    with _CARGA_LOCK:
        if _sessao is not None:
            return _sessao
        caminho = _exigir_arquivo(_RECONHECEDOR)
        try:
            import onnxruntime as ort
            opcoes = ort.SessionOptions()
            opcoes.intra_op_num_threads = min(4, max(1, os.cpu_count() or 1))
            opcoes.inter_op_num_threads = 1
            opcoes.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            sessao = ort.InferenceSession(
                str(caminho), sess_options=opcoes, providers=['CPUExecutionProvider'],
            )
            if len(sessao.get_inputs()) != 1:
                raise ValueError
        except Exception:
            raise ModeloFacialIndisponivel(
                'Não foi possível carregar AuraFace. Confira os modelos e o ONNX Runtime do backend.'
            ) from None
        _sessao = sessao
    return _sessao


def _validar_rgb(imagem: np.ndarray, tamanho: tuple[int, int] | None = None) -> None:
    if (not isinstance(imagem, np.ndarray) or imagem.ndim != 3 or imagem.shape[2] != 3
            or min(imagem.shape[:2]) < 1 or not np.issubdtype(imagem.dtype, np.number)
            or np.issubdtype(imagem.dtype, np.complexfloating)
            or (tamanho is not None and imagem.shape[:2] != tamanho)):
        raise ValueError('A inferência facial requer uma imagem RGB de dimensões válidas.')
    if not np.isfinite(imagem).all() or np.any(imagem < 0) or np.any(imagem > 255):
        raise ValueError('A imagem RGB contém pixels inválidos.')


def detectar_faces(rgb: np.ndarray) -> np.ndarray:
    """Retorna caixas, cinco pontos faciais e confiança YuNet em linhas de 15 valores."""
    _validar_rgb(rgb)
    detector = _carregar_detector()
    bgr = np.ascontiguousarray(rgb[:, :, ::-1], dtype=np.uint8)
    try:
        with _DETECCAO_LOCK:
            detector.setInputSize((rgb.shape[1], rgb.shape[0]))
            _, faces = detector.detect(bgr)
        if faces is None:
            return np.empty((0, 15), dtype=np.float32)
        faces = np.asarray(faces)
        if (faces.ndim != 2 or faces.shape[1] != 15
                or not np.issubdtype(faces.dtype, np.floating) or not np.isfinite(faces).all()):
            raise ValueError
        return faces.astype(np.float32, copy=False)
    except Exception:
        raise ModeloFacialIndisponivel('O detector facial não conseguiu processar a captura.') from None


def inferir_embedding(imagem112rgb: np.ndarray) -> np.ndarray:
    """Executa AuraFace em RGB NCHW e devolve 512 componentes L2 normalizados."""
    _validar_rgb(imagem112rgb, (112, 112))
    sessao = _carregar_sessao()
    tensor = (imagem112rgb.astype(np.float32) - 127.5) / 127.5
    tensor = np.ascontiguousarray(tensor.transpose(2, 0, 1)[None, ...])
    try:
        saidas = sessao.run(None, {sessao.get_inputs()[0].name: tensor})
        if len(saidas) != 1:
            raise ValueError
        saida = np.asarray(saidas[0])
        if saida.shape != (1, 512) or not np.issubdtype(saida.dtype, np.floating):
            raise ValueError
        vetor = saida[0].astype(np.float64)
        norma = float(np.linalg.norm(vetor))
        if not np.isfinite(vetor).all() or not np.isfinite(norma) or norma <= 1e-12:
            raise ValueError
        return vetor / norma
    except Exception:
        raise ModeloFacialIndisponivel('AuraFace produziu um embedding facial inválido.') from None


def _detectar_faces(rgb: np.ndarray) -> np.ndarray:
    try:
        return detectar_faces(rgb)
    except ModeloFacialIndisponivel as exc:
        raise BiometriaIndisponivel(str(exc)) from None


def _inferir_embedding(imagem: np.ndarray) -> np.ndarray:
    try:
        return inferir_embedding(imagem)
    except ModeloFacialIndisponivel as exc:
        raise BiometriaIndisponivel(str(exc)) from None


def segmentacao(processado):
    return _segmentacao(processado, _detectar_faces)


def extracao_caracteristicas(segmento):
    return _extracao_caracteristicas(segmento, _inferir_embedding)


# Coordenação das cinco fases


def processar_captura(
    frames: list[dict[str, Any]], *, exigir_movimento: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Cadastro: cinco quadros, com movimento e três amostras frontais.
    Login: três a cinco amostras frontais, sem a sequência de movimento.
    """

    if not isinstance(frames, list) or not 3 <= len(frames) <= 5:
        raise BiometriaErro("Capture de três a cinco quadros da câmera.")
    if exigir_movimento and len(frames) != 5:
        raise BiometriaErro(
            "Refaça a captura completa: olhe de frente, vire levemente para cada lado e volte a olhar para a câmera."
        )

    imagens, segmentos, assinaturas, qualidades = [], [], [], []
    formato = None

    for indice, frame in enumerate(frames, 1):
        try:
            rgb = sensoriamento(frame)
            if formato is not None and rgb.shape != formato:
                raise BiometriaErro("Todos os quadros devem ter as mesmas dimensões.")
            formato = rgb.shape
            imagens.append(rgb)
        except BiometriaErro as exc:
            _registrar_diagnostico(
                "captura", aceita=False, quadro=indice, motivo=str(exc),
            )
            raise type(exc)(f"Quadro {indice}: {exc}") from exc

    for indice, rgb in enumerate(imagens, 1):
        try:
            segmento = segmentacao(pre_processamento(rgb))
            segmentos.append(segmento)
            qualidades.append(segmento["qualidade"])
        except BiometriaErro as exc:
            _registrar_diagnostico("captura", aceita=False, quadro=indice, motivo=str(exc))
            raise type(exc)(f"Quadro {indice}: {exc}") from exc

    if exigir_movimento:
        for indice, rgb in enumerate(imagens, 1):
            if any(np.array_equal(rgb, anterior) for anterior in imagens[:indice - 1]):
                mensagem = "Os quadros repetem a mesma imagem. Refaça a captura: frente, um lado, outro lado e de volta para a câmera."
                _registrar_diagnostico("captura", aceita=False, quadro=indice, motivo=mensagem)
                raise BiometriaErro(f"Quadro {indice}: {mensagem}")
        _validar_movimento(segmentos)

    # As laterais servem apenas para conferir movimento. Comparar essas poses
    # com as frontais prejudica a consistência e a assinatura de uma pessoa real.
    indices_assinatura = [0, 3, 4] if exigir_movimento else list(range(len(segmentos)))
    for indice in indices_assinatura:
        try:
            assinaturas.append(extracao_caracteristicas(segmentos[indice]))
        except BiometriaErro as exc:
            _registrar_diagnostico("captura", aceita=False, quadro=indice + 1, motivo=str(exc))
            raise type(exc)(f"Quadro {indice + 1}: {exc}") from exc

    maior_distancia = max(
        comparar_assinaturas(a, b)
        for indice, a in enumerate(assinaturas) for b in assinaturas[indice + 1:]
    )

    _registrar_diagnostico(
        "captura", aceita=maior_distancia <= LIMITE_CONSISTENCIA,
        qualidade_quadros=qualidades,
        maior_distancia_entre_quadros=round(maior_distancia, 6),
        limite_consistencia=LIMITE_CONSISTENCIA,
        motivo="quadros_consistentes" if maior_distancia <= LIMITE_CONSISTENCIA else "quadros_inconsistentes",
    )

    if maior_distancia > LIMITE_CONSISTENCIA:
        raise BiometriaErro(
            "As imagens de frente não ficaram consistentes. Ao voltar para a câmera, pare o movimento e mantenha o rosto iluminado até concluir a captura."
        )

    assinatura = _criar_assinatura(np.mean([item["vetor"] for item in assinaturas], axis=0))
    assinatura["amostras"] = [item["vetor"] for item in assinaturas]
    resumo = {
        "etapas": [
            {"fase": "Sensores", "descricao": f"{len(frames)} quadros RGB recebidos da câmera.",
             "largura": formato[1], "altura": formato[0], "canais": formato[2]},
            {"fase": "Pré-processamento", "descricao": "Análise da luminância original e normalização fotométrica do rosto após o alinhamento (gamma e CLAHE)."},
            {"fase": "Segmentação", "descricao": "Detecção de um rosto com YuNet e alinhamento em 112×112."},
            {"fase": "Extração de características", "descricao": f"Embedding facial AuraFace com {DIMENSAO} componentes."},
            {"fase": "Classificação/interpretação", "descricao": "Comparação facial 1:1 por distância de cosseno."},
        ],
        "quadros": len(frames), "qualidade": qualidades,
        "quadros_assinatura": [indice + 1 for indice in indices_assinatura],
        "modelo": "AuraFace v1 / ArcFace ResNet100 / ONNX Runtime", "algoritmo": ALGORITMO,
        "maior_distancia_entre_quadros": round(maior_distancia, 6),
        "limite_consistencia_experimental": LIMITE_CONSISTENCIA,
        "foco_minimo_experimental": FOCO_MINIMO_EXPERIMENTAL, "guia": GUIA.copy(),
        "aviso": "Protótipo experimental sem prova de vida; não usar como único fator em produção.",
    }

    return assinatura, resumo


# API HTTP


COOKIE = 'aps_sessao'
DESAFIO_COOKIE = 'aps_desafio'
DESAFIO_SEGUNDOS = 120
MAX_BODY = 8 * 1024 * 1024


class ProtecoesHTTP:

    """
    Limita bytes antes do parser; bloqueia origens não autorizadas e rajadas.

    Limite em memória por IP/processo: executar um worker nesta demonstração.
    """
    def __init__(self, app, settings):

        self.app, self.settings = app, settings
        self.tentativas = defaultdict(deque)
        self.lock = Lock()

    async def __call__(self, scope, receive, send):

        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        scope.setdefault('state', {})['requisicao_id'] = str(uuid4())
        headers = dict(scope['headers'])
        api_write = scope['path'].startswith('/api/') and scope['method'] in {'POST', 'PUT', 'PATCH', 'DELETE'}

        async def reject(code, message):
            await JSONResponse({'detail': message}, status_code=code)(scope, receive, send_headers)

        async def send_headers(message):

            if message['type'] == 'http.response.start':

                message['headers'] = list(message.get('headers', [])) + [
                    (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'x-frame-options', b'DENY'), (b'referrer-policy', b'no-referrer'),
                    (b'permissions-policy', b'camera=(self), microphone=()'),
                    (b'x-request-id', scope['state']['requisicao_id'].encode()),
                ]

            await send(message)

        if api_write:

            origin = headers.get(b'origin', b'').decode('latin-1').rstrip('/')
            site = headers.get(b'sec-fetch-site')

            if (origin and origin not in self.settings.origins) or (not origin and site == b'cross-site'):
                return await reject(403, 'Origem não autorizada.')

            requer_json = scope['method'] in {'POST', 'PUT', 'PATCH'} and scope['path'] != '/api/sair'

            if requer_json and headers.get(b'content-type', b'').split(b';')[0].strip().lower() != b'application/json':
                return await reject(415, 'Envie application/json com quadros RGB da câmera.')

            ip = (scope.get('client') or ('local', 0))[0]
            now = monotonic()

            with self.lock:

                if len(self.tentativas) > 1000:
                    self.tentativas = defaultdict(deque, {k: v for k, v in self.tentativas.items() if v and now - v[-1] < 60})

                fila = self.tentativas[ip]

                while fila and now - fila[0] >= 60:
                    fila.popleft()

                blocked = len(fila) >= self.settings.rate_limit_per_minute

                if not blocked:
                    fila.append(now)

            if blocked:
                return await reject(429, 'Muitas tentativas. Aguarde um minuto.')

            raw_length = headers.get(b'content-length')

            if raw_length:

                try:
                    length = int(raw_length)

                except ValueError:
                    return await reject(400, 'Tamanho da requisição inválido.')

                if length < 0 or length > MAX_BODY:
                    return await reject(413, 'Captura acima do limite de 8 MiB.')

            body = bytearray()

            while True:

                message = await receive()

                if message['type'] == 'http.disconnect':
                    return

                body.extend(message.get('body', b''))

                if len(body) > MAX_BODY:
                    return await reject(413, 'Captura acima do limite de 8 MiB.')

                if not message.get('more_body', False):
                    break

            original_receive = receive
            pending = True

            async def receive_body():

                nonlocal pending

                if pending:
                    pending = False
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}

                return await original_receive()

            return await self.app(scope, receive_body, send_headers)

        return await self.app(scope, receive, send_headers)


def criar_app(settings: Settings | None = None, engine=None) -> FastAPI:

    settings = settings or Settings()
    db_engine = engine if engine is not None else criar_engine(settings)
    sessions = fabrica_sessoes(db_engine)
    seguranca = Seguranca(settings.biometric_key.get_secret_value())

    @asynccontextmanager
    async def lifespan(_app):

        try:
            with db_engine.connect() as connection:
                connection.execute(select(Usuario.id, Usuario.biometria_ref).limit(1))
                connection.execute(select(DesafioBiometrico.token_hash).limit(1))
                for tabela in (Dossie, DossieRecorte, DossieRegistro):
                    connection.execute(select(tabela.id).limit(1))

        except SQLAlchemyError:
            raise RuntimeError('Banco indisponível ou esquema desatualizado. Confira MySQL/.env e execute a inicialização ou scripts.migrar_banco para bancos antigos.') from None

        yield

        db_engine.dispose()

    app = FastAPI(title='APS • Biometria por câmera', version='2.1.0', lifespan=lifespan,
                  description='Protótipo acadêmico: segmentação guiada, sem detector pronto e sem prova de vida. '
                              'Após a verificação facial, os níveis 1, 2 e 3 recebem do servidor somente o recorte '
                              'de cada dossiê autorizado ao seu nível. O administrador (nível 4) gerencia usuários '
                              'e não consulta dossiês. Conteúdo fictício para demonstração.')
    app.state.engine = db_engine
    app.add_middleware(ProtecoesHTTP, settings=settings)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(settings.origins),
        allow_credentials=True,
        allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
        allow_headers=['Accept', 'Content-Type'],
    )

    def banco():

        with sessions() as session:

            try:
                yield session

            except Exception:
                session.rollback()
                raise

    def log(db, request, evento, sucesso, motivo, usuario_id=None):

        db.add(LogAcesso(usuario_id=usuario_id, evento=evento, sucesso=sucesso,
                        motivo=motivo, requisicao_id=request.state.requisicao_id))

    def negar(db, request, evento, motivo, status=401, mensagem='Não foi possível validar o usuário.', usuario_id=None):

        log(db, request, evento, False, motivo, usuario_id)
        db.commit()

        raise HTTPException(status, mensagem)

    def administrador(request: Request, db=Depends(banco)):
        token = request.cookies.get(COOKIE)
        sessao = db.get(Sessao, hash_token(token)) if token else None
        user = db.get(Usuario, sessao.usuario_id) if sessao and sessao.expira_em > agora() else None

        if not user or not user.ativo:
            negar(db, request, 'administracao', 'sessao_invalida', 401,
                  'Sessão ausente ou expirada. Entre novamente.')
        if user.nivel != 4:
            negar(db, request, 'administracao', 'nivel_insuficiente', 403,
                  'Acesso reservado ao administrador.', user.id)
        return user

    def captura(db, request, dados, evento):

        try:
            return processar_captura(
                [frame.model_dump() for frame in dados.frames],
                exigir_movimento=evento != 'verificacao',
            )

        except BiometriaIndisponivel as exc:
            negar(db, request, evento, 'modelo_indisponivel', 503, str(exc))
        except BiometriaErro as exc:
            negar(db, request, evento, 'captura_invalida', 422, str(exc))

    def assinatura(db, request, user, evento):

        try:
            return seguranca.decifrar(user.assinatura_cifrada, user.biometria_ref, 'biometria')

        except (InvalidTag, ValueError, TypeError):
            negar(db, request, evento, 'integridade_assinatura', 503,
                  'Assinatura indisponível. Confira a chave e a integridade do banco.', user.id)

    def publico(user):
        return {'id': user.id, 'nome': user.nome, 'nivel': user.nivel}

    def fingerprint_autorizacao(user):
        digest = hashlib.sha256(user.senha_hash.encode('utf-8') + b'\x00')
        digest.update(user.assinatura_cifrada or b'')
        return digest.hexdigest()

    def publico_administrativo(user):
        return {**publico(user), 'ativo': user.ativo,
                'criado_em': user.criado_em.isoformat(timespec='seconds') + 'Z'}

    def revogar_anterior(db, request):

        token = request.cookies.get(COOKIE)

        if token:
            db.execute(delete(Sessao).where(Sessao.token_hash == hash_token(token)))

    def revogar_desafio(db, request):

        token = request.cookies.get(DESAFIO_COOKIE)

        if token:
            db.execute(delete(DesafioBiometrico).where(DesafioBiometrico.token_hash == hash_token(token)))

    def limpar_cookies(response):

        for name in (COOKIE, DESAFIO_COOKIE):
            response.delete_cookie(name, path='/', secure=settings.cookie_secure,
                                   httponly=True, samesite='strict')

    def autenticar(db, request, response, user, processamento, evento, motivo='reconhecido'):

        token = secrets.token_urlsafe(32)
        db.execute(delete(Sessao).where(Sessao.expira_em <= agora()))
        db.add(Sessao(token_hash=hash_token(token), usuario_id=user.id,
                      expira_em=agora() + timedelta(minutes=settings.session_minutes)))
        log(db, request, evento, True, motivo, user.id)
        db.commit()
        response.set_cookie(COOKIE, token, max_age=settings.session_minutes * 60,
                            httponly=True, secure=settings.cookie_secure, samesite='strict', path='/')
        response.delete_cookie(DESAFIO_COOKIE, path='/', secure=settings.cookie_secure,
                               httponly=True, samesite='strict')

        return {'usuario': publico(user), 'processamento': processamento}

    @app.exception_handler(RequestValidationError)
    def validacao_erro(request, exc):

        erros = [{'loc': list(e['loc']), 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]
        resposta = JSONResponse({'detail': erros}, status_code=422)

        if request.url.path in ('/api/autenticacao/credenciais', '/api/autenticacao/verificar'):

            try:
                with sessions() as db:
                    revogar_anterior(db, request)
                    revogar_desafio(db, request)
                    db.commit()

            except SQLAlchemyError:
                resposta = JSONResponse({'detail': 'Banco indisponível.'}, status_code=503)

            limpar_cookies(resposta)

        return resposta

    @app.exception_handler(SQLAlchemyError)
    async def banco_erro(request, exc):

        resposta = JSONResponse({'detail': 'Banco indisponível. Verifique o serviço MySQL e a configuração local.'}, status_code=503)

        if request.url.path.startswith('/api/autenticacao/'):
            limpar_cookies(resposta)

        return resposta

    @app.exception_handler(HTTPException)
    async def http_erro(request, exc):

        resposta = JSONResponse({'detail': exc.detail}, status_code=exc.status_code, headers=exc.headers)

        preservar_desafio = request.url.path == '/api/autenticacao/verificar' \
            and getattr(request.state, 'preservar_desafio', False)
        if request.url.path.startswith('/api/autenticacao/') and not preservar_desafio:
            limpar_cookies(resposta)

        elif request.url.path == '/api/sessao':
            resposta.delete_cookie(COOKIE, path='/', secure=settings.cookie_secure, httponly=True, samesite='strict')

        return resposta

    @app.get('/api/saude', tags=['Sistema'])
    def saude(db=Depends(banco)):

        db.execute(text('SELECT 1'))

        return {'status': 'ok', 'banco': 'ok', 'algoritmo': ALGORITMO,
                'framework': 'ONNX Runtime', 'prova_de_vida': False}

    @app.post('/api/usuarios', status_code=201, tags=['Cadastro'], dependencies=[Depends(administrador)])
    def cadastrar(dados: Cadastro, request: Request, db=Depends(banco)):

        cpf_indice = seguranca.indice_cpf(dados.cpf)

        existente = db.scalar(select(Usuario).where(Usuario.cpf_indice == cpf_indice))

        if existente and (existente.nivel == 4 or existente.assinatura_cifrada is not None):
            negar(db, request, 'cadastro', 'cpf_duplicado', 409, 'CPF já cadastrado.')
        # Nenhum dado do usuário é persistido antes da captura ser aprovada.
        # Cadastros incompletos de versões anteriores podem ser retomados pelo CPF.
        sig, processamento = captura(db, request, dados, 'cadastro')
        if existente:
            # Outra captura pode ter concluído o mesmo cadastro enquanto os
            # modelos processavam estes quadros. Preserve o primeiro sucesso.
            db.refresh(existente, with_for_update=True)
            if existente.nivel == 4 or existente.assinatura_cifrada is not None:
                negar(db, request, 'cadastro', 'cpf_duplicado', 409, 'CPF já cadastrado.')
        referencia = existente.biometria_ref if existente else str(uuid4())
        user = existente if existente else Usuario(biometria_ref=referencia, cpf_indice=cpf_indice)
        user.nome = dados.nome
        user.cpf_cifrado = seguranca.cifrar({'cpf': dados.cpf}, referencia, 'cpf')
        user.senha_hash = seguranca.senhas.hash(dados.senha)
        user.nivel = dados.nivel
        user.ativo = True
        user.assinatura_cifrada = seguranca.cifrar(sig, referencia, 'biometria')

        try:
            db.add(user)
            if existente:
                db.execute(delete(Sessao).where(Sessao.usuario_id == user.id))
                db.execute(delete(DesafioBiometrico).where(DesafioBiometrico.usuario_id == user.id))
            db.flush()
            log(db, request, 'cadastro', True, 'cadastrado', user.id)
            db.commit()

        except IntegrityError:
            db.rollback()
            negar(db, request, 'cadastro', 'conflito_cadastro', 409, 'Cadastro já existente ou dados em conflito.')

        return {'usuario': publico(user), 'processamento': processamento}

    @app.get('/api/usuarios', tags=['Usuários'], dependencies=[Depends(administrador)])
    def listar_usuarios(db=Depends(banco)):

        usuarios = db.scalars(select(Usuario).where(
            (Usuario.nivel == 4) | Usuario.assinatura_cifrada.is_not(None)
        ).order_by(Usuario.id)).all()

        return {'usuarios': [publico_administrativo(user) for user in usuarios]}

    @app.patch('/api/usuarios/{usuario_id}', tags=['Usuários'], dependencies=[Depends(administrador)])
    def atualizar_usuario(usuario_id: int, dados: UsuarioAtualizacao,
                          request: Request, db=Depends(banco)):

        user = db.get(Usuario, usuario_id)

        if not user:
            raise HTTPException(404, 'Usuário não encontrado.')
        if user.nivel == 4:
            raise HTTPException(403, 'O administrador é reservado à inicialização do sistema.')

        if dados.nome is not None:
            user.nome = dados.nome

        if dados.nivel is not None:
            user.nivel = dados.nivel

        if dados.ativo is not None:
            user.ativo = dados.ativo

        if dados.senha is not None:
            user.senha_hash = seguranca.senhas.hash(dados.senha)

        if dados.senha is not None or dados.ativo is False:
            db.execute(delete(Sessao).where(Sessao.usuario_id == user.id))
            db.execute(delete(DesafioBiometrico).where(DesafioBiometrico.usuario_id == user.id))

        log(db, request, 'usuario_atualizado', True, 'atualizado', user.id)
        db.commit()

        return {'usuario': publico_administrativo(user)}

    @app.put('/api/usuarios/{usuario_id}/biometria', tags=['Usuários'], dependencies=[Depends(administrador)])
    def atualizar_biometria(usuario_id: int, dados: Captura,
                            request: Request, db=Depends(banco)):

        user = db.get(Usuario, usuario_id)

        if not user:
            raise HTTPException(404, 'Usuário não encontrado.')
        if user.nivel == 4:
            raise HTTPException(403, 'O administrador não utiliza biometria.')

        sig, processamento = captura(db, request, dados, 'biometria_atualizada')
        user.assinatura_cifrada = seguranca.cifrar(sig, user.biometria_ref, 'biometria')
        db.execute(delete(Sessao).where(Sessao.usuario_id == user.id))
        db.execute(delete(DesafioBiometrico).where(DesafioBiometrico.usuario_id == user.id))
        log(db, request, 'biometria_atualizada', True, 'recadastrada', user.id)
        db.commit()

        return {'usuario': publico_administrativo(user), 'processamento': processamento}

    @app.delete('/api/usuarios/{usuario_id}', status_code=204, tags=['Usuários'], dependencies=[Depends(administrador)])
    def excluir_usuario(usuario_id: int, request: Request, db=Depends(banco)):

        user = db.get(Usuario, usuario_id)

        if not user:
            raise HTTPException(404, 'Usuário não encontrado.')
        if user.nivel == 4:
            raise HTTPException(403, 'O administrador não pode ser excluído.')

        log(db, request, 'usuario_excluido', True, 'excluido', user.id)
        db.delete(user)
        db.commit()

        return Response(status_code=204)

    @app.post('/api/autenticacao/credenciais', tags=['Autenticação'])
    def validar_credenciais(dados: Credenciais, request: Request, response: Response, db=Depends(banco)):

        revogar_anterior(db, request)
        revogar_desafio(db, request)

        user = db.scalar(select(Usuario).where(Usuario.cpf_indice == seguranca.indice_cpf(dados.cpf)))

        if not seguranca.verificar_senha(dados.senha, user.senha_hash if user else None) or not user or not user.ativo:
            negar(db, request, 'credenciais', 'credenciais_invalidas', mensagem='CPF ou senha inválidos.')

        if seguranca.senhas.check_needs_rehash(user.senha_hash):
            user.senha_hash = seguranca.senhas.hash(dados.senha)
        if user.nivel == 4:
            autenticar(db, request, response, user, None, 'credenciais', motivo='administrador')
            return {'mensagem': 'CPF e senha confirmados. Sessão administrativa iniciada.',
                    'expira_em_segundos': settings.session_minutes * 60,
                    'usuario': publico(user)}

        if user.assinatura_cifrada is None:
            negar(db, request, 'credenciais', 'cadastro_incompleto', 403,
                  'O cadastro facial deste usuário não foi concluído. Peça ao administrador para refazer o cadastro.', user.id)

        token = secrets.token_urlsafe(32)
        db.execute(delete(DesafioBiometrico).where(DesafioBiometrico.expira_em <= agora()))
        db.add(DesafioBiometrico(token_hash=hash_token(token), usuario_id=user.id,
                                expira_em=agora() + timedelta(seconds=DESAFIO_SEGUNDOS),
                                senha_fingerprint=fingerprint_autorizacao(user)))
        log(db, request, 'credenciais', True, 'aguardando_biometria', user.id)
        db.commit()
        response.delete_cookie(COOKIE, path='/', secure=settings.cookie_secure, httponly=True, samesite='strict')
        response.set_cookie(DESAFIO_COOKIE, token, max_age=DESAFIO_SEGUNDOS,
                            httponly=True, secure=settings.cookie_secure, samesite='strict', path='/')

        return {'mensagem': 'CPF e senha confirmados. Continue com a biometria.',
                'expira_em_segundos': DESAFIO_SEGUNDOS, 'usuario': publico(user)}

    @app.post('/api/autenticacao/verificar', tags=['Autenticação'])
    def verificar(dados: Captura, request: Request, response: Response, db=Depends(banco)):

        revogar_anterior(db, request)

        token = request.cookies.get(DESAFIO_COOKIE)
        desafio = db.scalar(select(DesafioBiometrico).where(
            DesafioBiometrico.token_hash == hash_token(token)).with_for_update()) if token else None

        if not desafio:
            negar(db, request, 'verificacao', 'desafio_ausente', mensagem='Confirme CPF e senha antes da biometria.')
        user_id, fingerprint, expiracao = desafio.usuario_id, desafio.senha_fingerprint, desafio.expira_em

        if expiracao <= agora():
            db.delete(desafio)
            db.commit()
            negar(db, request, 'verificacao', 'desafio_expirado', mensagem='O prazo da biometria expirou. Informe CPF e senha novamente.')

        user = db.get(Usuario, user_id)

        if not user or not user.ativo or fingerprint_autorizacao(user) != fingerprint:
            db.delete(desafio)
            db.commit()
            negar(db, request, 'verificacao', 'desafio_invalidado', mensagem='A autorização mudou. Informe CPF e senha novamente.')
        request.state.preservar_desafio = True
        sig, processamento = captura(db, request, dados, 'verificacao')

        try:
            armazenada = assinatura(db, request, user, 'verificacao')
        except HTTPException:
            request.state.preservar_desafio = False
            db.delete(desafio)
            db.commit()
            raise

        try:
            resultado = classificacao_interpretacao(sig, [(str(user.id), armazenada)], settings.face_threshold, settings.face_margin)

        except BiometriaErro:
            request.state.preservar_desafio = False
            db.delete(desafio)
            negar(db, request, 'verificacao', 'assinatura_invalida', 503, 'Assinatura incompatível. Contate o operador.')

        if not resultado['identificado']:
            negar(db, request, 'verificacao', 'face_nao_corresponde', mensagem='CPF e senha foram confirmados, mas a biometria não correspondeu. Olhe de frente para a câmera, mantenha o rosto inteiro visível e fique parado durante a captura.')

        processamento['classificacao_interpretacao'] = resultado
        db.refresh(user, with_for_update=True)

        if not user.ativo or fingerprint_autorizacao(user) != fingerprint:
            request.state.preservar_desafio = False
            db.delete(desafio)
            db.commit()
            negar(db, request, 'verificacao', 'desafio_invalidado', mensagem='A autorização mudou. Informe CPF e senha novamente.')

        db.delete(desafio)
        return autenticar(db, request, response, user, processamento, 'verificacao')

    @app.get('/api/sessao', tags=['Sessão'])
    def sessao(request: Request, db=Depends(banco)):
        token = request.cookies.get(COOKIE)
        session = db.get(Sessao, hash_token(token)) if token else None
        user = db.get(Usuario, session.usuario_id) if session and session.expira_em > agora() else None
        if not user or not user.ativo:
            raise HTTPException(401, 'Sessão ausente ou expirada. Valide seu rosto novamente.')
        return {'usuario': publico(user), 'mensagem': f'Você é do nível {user.nivel}'}

    def leitor_dossies(request: Request, db=Depends(banco)):
        """Exige a sessão concedida após a biometria e um nível de consulta (1 a 3)."""
        token = request.cookies.get(COOKIE)
        sessao = db.get(Sessao, hash_token(token)) if token else None
        user = db.get(Usuario, sessao.usuario_id) if sessao and sessao.expira_em > agora() else None

        if not user or not user.ativo:
            negar(db, request, 'dossie', 'sessao_invalida', 401,
                  'Sessão ausente ou expirada. Entre novamente para consultar os dossiês.')
        if user.nivel not in (1, 2, 3):
            negar(db, request, 'dossie', 'perfil_sem_dossies', 403,
                  'O administrador gerencia usuários e não consulta dossiês.', user.id)
        return user

    def dados_dossie(dossie):
        return {'codigo': dossie.codigo, 'titulo': dossie.titulo, 'situacao': dossie.situacao,
                'divisao': dossie.divisao, 'atualizado_em': dossie.atualizado_em.isoformat()}

    @app.get('/api/dossies', tags=['Dossiês'])
    def listar_dossies(user=Depends(leitor_dossies), db=Depends(banco)):

        linhas = db.execute(
            select(Dossie, DossieRecorte)
            .join(DossieRecorte, DossieRecorte.dossie_id == Dossie.id)
            .where(DossieRecorte.nivel == user.nivel)
            .order_by(Dossie.atualizado_em.desc(), Dossie.codigo)
        ).all()
        abertos = defaultdict(int)
        recortes = [recorte.id for _dossie, recorte in linhas]

        if recortes:
            consulta = select(DossieRegistro.recorte_id, DossieRegistro.tipo).where(
                DossieRegistro.recorte_id.in_(recortes),
                DossieRegistro.tipo.in_(('pendencia', 'decisao')),
                DossieRegistro.situacao.in_(SITUACOES_ABERTAS))
            for recorte_id, tipo in db.execute(consulta):
                abertos[(recorte_id, tipo)] += 1

        return {'nivel': user.nivel, 'dossies': [
            {**dados_dossie(dossie), 'resumo': recorte.resumo,
             'pendencias_abertas': abertos[(recorte.id, 'pendencia')],
             'decisoes_pendentes': abertos[(recorte.id, 'decisao')]}
            for dossie, recorte in linhas
        ]}

    @app.get('/api/dossies/{codigo}', tags=['Dossiês'])
    def consultar_dossie(codigo: str, request: Request, user=Depends(leitor_dossies), db=Depends(banco)):

        nao_liberado = 'Dossiê inexistente ou não liberado para o seu nível de acesso.'
        codigo = codigo.strip().upper()

        if not re.fullmatch(r'DOS-\d{4}-\d{3}', codigo):
            negar(db, request, 'dossie', 'codigo_invalido', 404, nao_liberado, user.id)

        linha = db.execute(
            select(Dossie, DossieRecorte)
            .outerjoin(DossieRecorte, (DossieRecorte.dossie_id == Dossie.id)
                       & (DossieRecorte.nivel == user.nivel))
            .where(Dossie.codigo == codigo)
        ).first()

        # Mesma resposta para inexistente e não autorizado: não revela quais dossiês existem.
        if not linha or linha[1] is None:
            motivo = 'sem_recorte' if linha else 'inexistente'
            negar(db, request, 'dossie', f'{motivo} {codigo}', 404, nao_liberado, user.id)

        dossie, recorte = linha
        registros = db.scalars(select(DossieRegistro).where(DossieRegistro.recorte_id == recorte.id)
                               .order_by(DossieRegistro.ordem, DossieRegistro.id)).all()
        por_tipo = {tipo: [r for r in registros if r.tipo == tipo] for tipo in TIPOS_REGISTRO}

        def item(registro):
            return {'titulo': registro.titulo, 'descricao': registro.descricao,
                    'prazo': registro.data.isoformat() if registro.data else None,
                    'situacao': registro.situacao}

        log(db, request, 'dossie', True, f'consultado {codigo}', user.id)
        db.commit()

        return {'nivel': user.nivel, 'dossie': dados_dossie(dossie), 'recorte': {
            'nivel': recorte.nivel, 'resumo': recorte.resumo, 'orientacao': recorte.orientacao,
            'campos': [{'rotulo': r.titulo, 'valor': r.descricao or ''} for r in por_tipo['campo']],
            'pendencias': [item(r) for r in por_tipo['pendencia']],
            'decisoes': [item(r) for r in por_tipo['decisao']],
            'historico': [{'data': r.data.isoformat() if r.data else None, 'descricao': r.titulo}
                          for r in sorted(por_tipo['historico'], key=lambda r: (r.data or date.min, r.ordem))],
        }}

    @app.post('/api/sair', tags=['Sessão'])
    def sair(request: Request, response: Response, db=Depends(banco)):
        revogar_anterior(db, request)
        revogar_desafio(db, request)
        db.commit()
        limpar_cookies(response)
        return {'mensagem': 'Sessão encerrada.'}

    @app.get('/', include_in_schema=False)
    def inicio():
        return RedirectResponse('/docs')

    return app


def __getattr__(name):
    # Uvicorn resolves app.main:app; CLI imports do not initialize settings.
    if name == 'app':
        application = criar_app()
        globals()['app'] = application
        return application
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
