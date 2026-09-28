# Processamento de imagens e assinatura biométrica

O núcleo está isolado em `app/biometria.py`. O módulo recebe quadros RGB vivos,
controla a qualidade, recorta a região facial guiada, executa o TensorFlow e
compara embeddings. Rotas, banco e front não implementam operações de visão.

## Fluxo

```text
getUserMedia → canvas RGB → 3 quadros → sensoriamento
→ pré-processamento → segmentação → MobileNetV2
→ embedding médio criptografado → comparação por cosseno
```

O painel usa `navigator.mediaDevices.getUserMedia()`. A prévia é espelhada
somente por CSS; os pixels enviados mantêm a orientação da câmera. Cada quadro
tem 320×240 pixels e três bytes RGB por pixel, codificados em Base64:

```json
{"largura": 320, "altura": 240, "rgb_base64": "BASE64_DOS_BYTES_RGB"}
```

Base64 é transporte, não prova de origem. Um cliente modificado ainda pode
enviar uma foto ou tela. A aplicação não implementa prova de vida.

## Cinco fases em `app/biometria.py`

1. `sensoriamento`: valida dimensões, Base64 e quantidade exata de pixels.
2. `pre_processamento`: aplica suavização binomial 3×3 e calcula luminância.
3. `segmentacao`: mede iluminação, contraste, saturação e foco na elipse; recorta
   a região facial e coloca fundo neutro fora da máscara.
4. `extracao_caracteristicas`: redimensiona para a entrada da MobileNetV2,
   aplica `mobilenet_v2.preprocess_input` e extrai 1.280 características com
   TensorFlow. O vetor é normalizado pela norma L2.
5. `classificacao_interpretacao`: calcula distância de cosseno normalizada e
   aplica limiar/margem experimentais.

O modelo é criado uma única vez por processo com `include_top=False`,
`pooling="avg"` e pesos `imagenet`. Na primeira captura o Keras baixa os pesos
para o cache local; depois eles são reutilizados.

## Assinatura versionada

```json
{
  "versao": 2,
  "algoritmo": "tensorflow-mobilenetv2-imagenet-face-roi-v2",
  "dimensao": 1280,
  "vetor": [0.0123, -0.0042]
}
```

O vetor do exemplo está abreviado. A assinatura real contém 1.280 números e
norma L2 igual a 1. Assinaturas antigas do algoritmo
`aps-lbp59-gradientes-v1` são rejeitadas e devem ser recadastradas; isso impede
comparações inválidas entre espaços vetoriais diferentes.

O lote final é a média normalizada dos três embeddings. Quadros muito
divergentes são recusados antes do armazenamento. A comparação usa:

```text
distância = (1 - cosseno(a, b)) / 2
```

Zero representa embeddings iguais. O limite inicial `FACE_THRESHOLD=0.20` é
experimental e precisa ser calibrado com capturas genuínas e impostoras.

## Persistência e limites

Os quadros existem apenas na memória durante a requisição. O banco recebe o
embedding serializado, compactado e cifrado com AES-256-GCM; CPF e senha seguem
as proteções descritas no README. Logs e respostas não incluem pixels nem vetor.

A MobileNetV2 foi treinada para classificação geral do ImageNet, não para
reconhecimento facial nem anti-spoofing. O uso do TensorFlow melhora a extração
de representações visuais em relação ao descritor artesanal anterior, mas não
transforma o protótipo em controle de acesso validado. Antes de uso real:

- adote detector/alinhamento facial e modelo treinado para faces;
- implemente prova de vida e defesa contra apresentação;
- meça FAR e FRR em conjuntos separados de calibração e avaliação;
- proteja os endpoints administrativos com autenticação e HTTPS;
- obtenha consentimento e defina retenção para dados biométricos.
