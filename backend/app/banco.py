"""Persistência v2: IDs inteiros e referência criptográfica estável por usuário."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Computed, DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint, create_engine
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, validates

from .config import Settings


def agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = 'usuarios'
    __table_args__ = (
        CheckConstraint('nivel BETWEEN 1 AND 4', name='ck_usuario_nivel'),
        CheckConstraint('nivel = 4 OR assinatura_cifrada IS NOT NULL', name='ck_usuario_assinatura'),
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


def criar_engine(settings: Settings):
    
    return create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=1800,
                         connect_args={'connect_timeout': 5}, hide_parameters=True)


def fabrica_sessoes(engine):
    
    return sessionmaker(bind=engine, expire_on_commit=False)
