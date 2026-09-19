import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class Cadastro(Credenciais, Captura):
    nome: str = Field(min_length=2, max_length=120)
    nivel: Annotated[int, Field(strict=True, ge=1, le=3)]

    @field_validator('nome')
    @classmethod
    def nome_valido(cls, value: str) -> str:
        value = ' '.join(value.split())
        if len(value) < 2 or any(ord(c) < 32 for c in value):
            raise ValueError('Informe o nome do usuário.')
        return value
