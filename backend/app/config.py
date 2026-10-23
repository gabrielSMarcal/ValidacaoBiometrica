import base64
import secrets
from pathlib import Path

from argon2 import extract_parameters
from argon2.exceptions import InvalidHashError
from argon2.low_level import Type
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

from .esquemas import normalizar_cpf

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
    allowed_origins: str = ('http://127.0.0.1:5500,http://localhost:5500,'
                            'http://127.0.0.1:8080,http://localhost:8080')
    face_threshold: float = Field(default=0.30, gt=0, le=0.40)
    face_margin: float = Field(default=0.03, gt=0, le=1)
    session_minutes: int = Field(default=15, ge=1, le=120)
    cookie_secure: bool = False
    rate_limit_per_minute: int = Field(default=20, ge=1, le=300)

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
