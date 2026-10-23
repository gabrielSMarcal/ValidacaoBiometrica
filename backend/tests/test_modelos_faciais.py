from dataclasses import replace
import hashlib
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from app import modelos_faciais as modelos


@pytest.fixture(autouse=True)
def runtime_local(tmp_path, monkeypatch):
    monkeypatch.setattr(modelos, 'DIRETORIO_MODELOS', tmp_path / 'modelos')
    monkeypatch.setattr(modelos, '_detector', None)
    monkeypatch.setattr(modelos, '_sessao', None)


@pytest.mark.parametrize('carregar', ['_carregar_detector', '_carregar_sessao'])
def test_modelo_ausente_falha_sem_baixar_automaticamente(monkeypatch, carregar):
    baixar = Mock(side_effect=AssertionError('Inferência não deve acessar a rede.'))
    monkeypatch.setattr(modelos, 'urlopen', baixar)
    with pytest.raises(modelos.ModeloFacialIndisponivel, match='ausente ou inválido'):
        getattr(modelos, carregar)()
    baixar.assert_not_called()


def test_modelo_com_tamanho_correto_e_sha_incorreto_nao_e_carregado(monkeypatch):
    modelos.DIRETORIO_MODELOS.mkdir()
    destino = modelos.DIRETORIO_MODELOS / modelos._DETECTOR.arquivo
    destino.write_bytes(b'x' * modelos._DETECTOR.tamanho)
    baixar = Mock(side_effect=AssertionError('Carregamento não deve baixar modelos.'))
    monkeypatch.setattr(modelos, 'urlopen', baixar)
    with pytest.raises(modelos.ModeloFacialIndisponivel, match='ausente ou inválido'):
        modelos._carregar_detector()
    assert modelos._detector is None
    baixar.assert_not_called()


def _modelo_pequeno(conteudo):
    return replace(modelos._DETECTOR, tamanho=len(conteudo),
                   sha256=hashlib.sha256(conteudo).hexdigest())


def test_preparacao_instala_apenas_modelo_verificado_e_reutiliza_arquivo(monkeypatch):
    conteudo = b'modelo-sintetico-para-teste-de-integridade'
    modelo = _modelo_pequeno(conteudo)
    baixar = Mock(side_effect=lambda *_args, **_kwargs: BytesIO(conteudo))
    monkeypatch.setattr(modelos, '_MODELOS', (modelo,))
    monkeypatch.setattr(modelos, 'urlopen', baixar)
    modelos.preparar_modelos()
    assert (modelos.DIRETORIO_MODELOS / modelo.arquivo).read_bytes() == conteudo
    assert modelos._arquivo_valido(modelo)
    assert list(modelos.DIRETORIO_MODELOS.glob('*.part')) == []
    modelos.preparar_modelos()
    assert baixar.call_count == 1
    assert baixar.call_args.args[0].full_url == modelo.url


@pytest.mark.parametrize('resposta', [b'ab', b'abcde', b'zzzz'])
def test_download_truncado_grande_ou_com_sha_incorreto_preserva_destino(monkeypatch, resposta):
    modelo = _modelo_pequeno(b'abcd')
    modelos.DIRETORIO_MODELOS.mkdir()
    destino = modelos.DIRETORIO_MODELOS / modelo.arquivo
    destino.write_bytes(b'arquivo-anterior')
    monkeypatch.setattr(modelos, '_MODELOS', (modelo,))
    monkeypatch.setattr(modelos, 'urlopen', lambda *_args, **_kwargs: BytesIO(resposta))
    with pytest.raises(modelos.ModeloFacialIndisponivel):
        modelos.preparar_modelos()
    assert destino.read_bytes() == b'arquivo-anterior'
    assert list(modelos.DIRETORIO_MODELOS.glob('*.part')) == []


def test_falha_de_rede_remove_parcial_e_oculta_erro_externo(monkeypatch):
    baixar = Mock(side_effect=OSError('segredo-do-servidor-nao-pode-sair'))
    monkeypatch.setattr(modelos, 'urlopen', baixar)
    with pytest.raises(modelos.ModeloFacialIndisponivel) as erro:
        modelos.preparar_modelos()
    assert 'segredo-do-servidor' not in str(erro.value)
    assert list(modelos.DIRETORIO_MODELOS.glob('*.part')) == []


def _sessao_falsa(monkeypatch, saida):
    executar = Mock(return_value=[saida])
    sessao = SimpleNamespace(get_inputs=lambda: [SimpleNamespace(name='rgb')], run=executar)
    monkeypatch.setattr(modelos, '_sessao', sessao)
    return executar


def test_aura_recebe_rgb_nchw_normalizado_e_retorna_512_componentes(monkeypatch):
    executar = _sessao_falsa(monkeypatch, np.ones((1, 512), dtype=np.float32))
    imagem = np.zeros((112, 112, 3), dtype=np.uint8)
    imagem[:, :, 0] = 255
    vetor = modelos.inferir_embedding(imagem)
    tensor = executar.call_args.args[1]['rgb']
    assert tensor.shape == (1, 3, 112, 112) and tensor.dtype == np.float32
    assert np.all(tensor[:, 0] == 1) and np.all(tensor[:, 1:] == -1)
    assert vetor.shape == (512,) and np.isfinite(vetor).all()
    assert np.linalg.norm(vetor) == pytest.approx(1.0)


@pytest.mark.parametrize('saida', [
    np.ones((1, 1280), dtype=np.float32),
    np.ones((512,), dtype=np.float32),
    np.ones((1, 512), dtype=np.int64),
    np.zeros((1, 512), dtype=np.float32),
    np.full((1, 512), np.nan, dtype=np.float32),
    np.full((1, 512), np.inf, dtype=np.float32),
])
def test_embedding_invalido_falha_fechado(monkeypatch, saida):
    _sessao_falsa(monkeypatch, saida)
    with pytest.raises(modelos.ModeloFacialIndisponivel, match='embedding facial inválido'):
        modelos.inferir_embedding(np.zeros((112, 112, 3), dtype=np.uint8))


def test_yunet_recebe_bgr_e_dimensao_real_da_captura(monkeypatch):
    detectar = Mock(return_value=(1, np.ones((1, 15), dtype=np.float32)))
    tamanho = Mock()
    monkeypatch.setattr(modelos, '_detector', SimpleNamespace(setInputSize=tamanho, detect=detectar))
    imagem = np.zeros((240, 320, 3), dtype=np.uint8)
    imagem[:, :, 0] = 255
    faces = modelos.detectar_faces(imagem)
    tamanho.assert_called_once_with((320, 240))
    bgr = detectar.call_args.args[0]
    assert np.all(bgr[:, :, 2] == 255) and np.all(bgr[:, :, :2] == 0)
    assert bgr.flags.c_contiguous and faces.shape == (1, 15)


def test_yunet_sem_rosto_retorna_matriz_vazia(monkeypatch):
    monkeypatch.setattr(modelos, '_detector', SimpleNamespace(
        setInputSize=Mock(), detect=Mock(return_value=(0, None)),
    ))
    assert modelos.detectar_faces(np.zeros((240, 320, 3), dtype=np.uint8)).shape == (0, 15)


@pytest.mark.parametrize('saida', [
    np.ones((1, 14), dtype=np.float32),
    np.ones((1, 15), dtype=np.int64),
    np.full((1, 15), np.nan, dtype=np.float32),
])
def test_saida_yunet_invalida_falha_fechada(monkeypatch, saida):
    monkeypatch.setattr(modelos, '_detector', SimpleNamespace(
        setInputSize=Mock(), detect=Mock(return_value=(1, saida)),
    ))
    with pytest.raises(modelos.ModeloFacialIndisponivel):
        modelos.detectar_faces(np.zeros((240, 320, 3), dtype=np.uint8))
