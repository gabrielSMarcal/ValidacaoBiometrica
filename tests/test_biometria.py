"""Testes sintéticos de contratos e rejeição; não medem acurácia facial."""

import base64
import copy
import json

import numpy as np
import pytest

from app.biometria import (
    ALGORITMO,
    DIMENSAO,
    BiometriaErro,
    classificacao_interpretacao,
    comparar_assinaturas,
    extracao_caracteristicas,
    pre_processamento,
    processar_captura,
    segmentacao,
    sensoriamento,
)


def quadro_sintetico(tipo=0, brilho=0, largura=320, altura=240):
    y, x = np.mgrid[:altura, :largura]
    if tipo == 0:
        textura = 120 + 35 * np.sin(x * 0.47) + 35 * np.cos(y * 0.29)
    else:
        textura = 120 + 45 * np.sin((x + y) * 0.61) + 25 * np.cos((x - y) * 0.71)
    cinza = np.clip(textura + brilho, 0, 255).astype(np.uint8)
    rgb = np.repeat(cinza[:, :, None], 3, axis=2)
    return {"largura": largura, "altura": altura, "rgb_base64": base64.b64encode(rgb.tobytes()).decode("ascii")}


def assinatura_sintetica(tipo=0, brilho=0):
    frame = quadro_sintetico(tipo=tipo, brilho=brilho)
    return processar_captura([frame] * 3)[0]


def test_pipeline_gera_assinatura_json_e_resumo_das_cinco_fases():
    frame = quadro_sintetico()
    assinatura, resumo = processar_captura([frame] * 3)
    assert assinatura["algoritmo"] == ALGORITMO
    assert assinatura["dimensao"] == DIMENSAO == 1136
    assert len(assinatura["vetor"]) == DIMENSAO
    assert sum(assinatura["vetor"]) == pytest.approx(1, abs=1e-7)
    assert all(valor >= 0 for valor in assinatura["vetor"])
    assert len(resumo["etapas"]) == 5
    assert len(resumo["qualidade"]) == 3
    assert resumo["maior_distancia_entre_quadros"] == 0
    serializado = json.dumps({"assinatura": assinatura, "resumo": resumo}, allow_nan=False)
    assert "rgb_base64" not in serializado
    assert "imagem" not in resumo and "mascara" not in resumo


def test_sensor_preserva_ordem_rgb_e_dimensoes():
    rgb = np.zeros((120, 160, 3), dtype=np.uint8)
    rgb[1, 2] = [10, 20, 30]
    frame = {"largura": 160, "altura": 120, "rgb_base64": base64.b64encode(rgb.tobytes()).decode()}
    recebido = sensoriamento(frame)
    np.testing.assert_array_equal(recebido[1, 2], [10, 20, 30])
    assert recebido.shape == (120, 160, 3)


@pytest.mark.parametrize("alteracao", [
    {"largura": True}, {"altura": "240"}, {"largura": 0}, {"altura": 481},
    {"rgb_base64": "data:image/png;base64,aGVsbG8="}, {"rgb_base64": None},
    {"rgb_base64": "!" * (320 * 240 * 4)},
    {"rgb_base64": "A" * (320 * 240 * 4 - 1) + "="},
])
def test_sensor_rejeita_tipo_dimensao_formato_e_buffer_invalido(alteracao):
    frame = quadro_sintetico()
    frame.update(alteracao)
    with pytest.raises(BiometriaErro):
        sensoriamento(frame)


@pytest.mark.parametrize("quantidade", [0, 1, 2, 6])
def test_captura_exige_tres_a_cinco_quadros(quantidade):
    with pytest.raises(BiometriaErro, match="três a cinco"):
        processar_captura([quadro_sintetico()] * quantidade)


def test_captura_rejeita_dimensoes_diferentes():
    a, b = quadro_sintetico(), quadro_sintetico(largura=160, altura=120)
    with pytest.raises(BiometriaErro, match="mesmas dimensões"):
        processar_captura([a, b, a])


@pytest.mark.parametrize("nivel,mensagem", [(0, "iluminação"), (255, "iluminação"), (120, "contraste")])
def test_qualidade_rejeita_escuro_estourado_e_sem_textura(nivel, mensagem):
    with pytest.raises(BiometriaErro, match=mensagem):
        segmentacao(pre_processamento(np.full((240, 320, 3), nivel, np.uint8)))


def test_qualidade_rejeita_imagem_sem_foco_mas_com_contraste():
    gradiente = np.tile(np.linspace(10, 240, 320, dtype=np.uint8), (240, 1))
    with pytest.raises(BiometriaErro, match="nítida"):
        segmentacao(pre_processamento(np.repeat(gradiente[:, :, None], 3, axis=2)))


def test_distancia_simetrica_identidade_e_estabilidade_a_brilho():
    a, b, outra = assinatura_sintetica(), assinatura_sintetica(brilho=15), assinatura_sintetica(tipo=1)
    assert comparar_assinaturas(a, a) == pytest.approx(0)
    assert comparar_assinaturas(a, outra) == pytest.approx(comparar_assinaturas(outra, a))
    assert comparar_assinaturas(a, b) < 0.08
    assert 0.20 < comparar_assinaturas(a, outra) <= 1


def test_captura_rejeita_texturas_inconsistentes():
    a, b = quadro_sintetico(), quadro_sintetico(tipo=1)
    with pytest.raises(BiometriaErro, match="diferem muito"):
        processar_captura([a, b, a])


def test_classificacao_identifica_e_rejeita_fora_do_limiar():
    a, b = assinatura_sintetica(), assinatura_sintetica(tipo=1)
    resultado = classificacao_interpretacao(a, [("1", a), ("2", b)])
    assert resultado["identificado"] is True
    assert resultado["usuario_id"] == "1"
    rejeitado = classificacao_interpretacao(a, [("2", b)])
    assert rejeitado["identificado"] is False
    assert rejeitado["usuario_id"] is None
    assert rejeitado["motivo"] == "fora_do_limiar"


def test_classificacao_rejeita_empate_e_base_vazia():
    assinatura = assinatura_sintetica()
    empate = classificacao_interpretacao(assinatura, [("1", assinatura), ("2", assinatura)], margem=0)
    assert empate["motivo"] == "captura_ambigua"
    assert empate["usuario_id"] is None
    vazio = classificacao_interpretacao(assinatura, [])
    assert vazio["motivo"] == "sem_candidatos"
    assert vazio["distancia"] is None


def test_classificacao_aplica_margem_entre_primeiro_e_segundo_candidatos():
    a, b = assinatura_sintetica(), assinatura_sintetica(brilho=15)
    distancia = comparar_assinaturas(a, b)
    resultado = classificacao_interpretacao(a, [("1", a), ("2", b)], margem=distancia + 0.01)
    assert resultado["motivo"] == "captura_ambigua"
    assert resultado["segunda_distancia"] == pytest.approx(distancia)


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), -0.01, 1.01, True, 10**400])
def test_classificacao_rejeita_limiares_invalidos(valor):
    with pytest.raises(BiometriaErro, match="Limiar"):
        classificacao_interpretacao(assinatura_sintetica(), [], limiar=valor)


@pytest.mark.parametrize("alteracao", [
    {"versao": 2}, {"algoritmo": "outro"}, {"dimensao": 1}, {"vetor": []},
    {"vetor": [float("nan")] * DIMENSAO}, {"vetor": [0] * DIMENSAO},
    {"vetor": ["0.001"] * DIMENSAO}, {"vetor": [-1] * DIMENSAO},
])
def test_comparacao_rejeita_assinaturas_malformadas(alteracao):
    assinatura = assinatura_sintetica()
    invalida = copy.deepcopy(assinatura)
    invalida.update(alteracao)
    with pytest.raises(BiometriaErro):
        comparar_assinaturas(assinatura, invalida)


def test_extracao_rejeita_mascara_vazia():
    segmento = segmentacao(pre_processamento(sensoriamento(quadro_sintetico())))
    segmento["mascara"][:] = False
    with pytest.raises(BiometriaErro, match="vazia"):
        extracao_caracteristicas(segmento)
