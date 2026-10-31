"""5. Classificação: compara assinaturas, aplica limiar e interpreta o resultado."""
from __future__ import annotations
import math
from typing import Any
import numpy as np
from .sensoriamento import BiometriaErro, _registrar_diagnostico
from .extracao_caracteristicas import ALGORITMO, VERSAO, DIMENSAO, _validar_assinatura


LIMIAR_EXPERIMENTAL = 0.30
LIMIAR_MAXIMO = 0.40
MARGEM_EXPERIMENTAL = 0.03
LIMITE_CONSISTENCIA = 0.25


def comparar_assinaturas(a: dict[str, Any], b: dict[str, Any]) -> float:
    """
    Distância de cosseno em [0, 2]; zero indica embeddings iguais.
    """

    va, vb = _validar_assinatura(a), _validar_assinatura(b)

    return 1 - float(np.clip(np.dot(va, vb), -1, 1))


def classificacao_interpretacao(
    assinatura: dict[str, Any], candidatos: list[tuple[str, dict[str, Any]]],
    limiar: float = LIMIAR_EXPERIMENTAL, margem: float = MARGEM_EXPERIMENTAL,
) -> dict[str, Any]:
    """
    5. Classificação: vizinho mais próximo com limiar e margem.
    """

    _validar_assinatura(assinatura)

    for valor, maximo in ((limiar, LIMIAR_MAXIMO), (margem, 1)):
        if type(valor) not in (int, float) or not 0 <= valor <= maximo or not math.isfinite(valor):
            raise BiometriaErro("Limiar ou margem fora do intervalo permitido pelo modelo facial.")

    if not isinstance(candidatos, list):
        raise BiometriaErro("Os candidatos devem ser uma lista de identificadores e assinaturas.")

    resultados, ids, diagnosticos = [], set(), {}

    for candidato in candidatos:

        if not isinstance(candidato, (tuple, list)) or len(candidato) != 2:
            raise BiometriaErro("Candidato biométrico inválido.")

        usuario_id, cadastrada = candidato

        if not isinstance(usuario_id, str) or not usuario_id or usuario_id in ids:
            raise BiometriaErro("Cada candidato deve possuir um identificador único.")

        ids.add(usuario_id)
        distancia_media = comparar_assinaturas(assinatura, cadastrada)
        distancia = distancia_media
        distancias_quadros = []
        amostras = assinatura.get("amostras", [])
        if not isinstance(amostras, list) or (amostras and not 3 <= len(amostras) <= 5):
            raise BiometriaErro("Amostras da assinatura biométrica inválidas.")
        for vetor in amostras:
            amostra = {"versao": VERSAO, "algoritmo": ALGORITMO, "dimensao": DIMENSAO, "vetor": vetor}
            distancia_quadro = comparar_assinaturas(amostra, cadastrada)
            distancias_quadros.append(distancia_quadro)
            distancia = max(distancia, distancia_quadro)
        resultados.append((distancia, usuario_id))
        diagnosticos[usuario_id] = {
            "distancia_media": round(distancia_media, 6),
            "distancias_quadros": [round(valor, 6) for valor in distancias_quadros],
            "quadros_fora_do_limiar": [
                indice for indice, valor in enumerate(distancias_quadros, 1) if valor > limiar
            ],
        }

    resultados.sort()
    resultado = {"identificado": False, "usuario_id": None, "distancia": None,
                 "segunda_distancia": None, "motivo": "sem_candidatos"}

    if not resultados:
        return resultado

    melhor, usuario_id = resultados[0]
    segunda = resultados[1][0] if len(resultados) > 1 else None
    resultado.update(distancia=melhor, segunda_distancia=segunda)

    if melhor > limiar:
        resultado["motivo"] = "fora_do_limiar"

    elif segunda is not None and (segunda - melhor < margem or segunda == melhor):
        resultado["motivo"] = "captura_ambigua"

    else:
        resultado.update(identificado=True, usuario_id=usuario_id, motivo="identificado")

    _registrar_diagnostico(
        "comparacao", **diagnosticos[usuario_id],
        distancia_decisao=round(melhor, 6),
        segunda_distancia=round(segunda, 6) if segunda is not None else None,
        limiar=limiar, margem=margem, candidatos=len(resultados),
        identificado=resultado["identificado"], motivo=resultado["motivo"],
    )

    return resultado
