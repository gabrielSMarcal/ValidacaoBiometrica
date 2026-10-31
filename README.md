# APS — Processamento de imagens e reconhecimento facial

O objetivo principal do projeto é aplicar os estágios do processamento de imagens à autenticação facial de usuários:

**Aquisição → Pré-processamento → Segmentação → Extração de características → Classificação e interpretação**

O backend organiza essas etapas em funções próprias. Os modelos treinados participam da localização do rosto e da extração de suas características; a aplicação coordena a qualidade da captura, a geração da assinatura biométrica e a decisão de autenticação.

## Executar a aplicação

Os dois inicializadores ficam na raiz do repositório:

```powershell
# Windows
.\iniciar.bat
```

```bash
# Linux
bash ./iniciar.sh
```

Antes de executar, inicie o MySQL, configure `backend/.env` e tenha Node.js/npm e um ambiente Python 3.12 funcional. Os scripts priorizam a `.venv` da raiz e reutilizam `backend/.venv` quando necessário; não criam outro ambiente nem duplicam modelos automaticamente. Se ainda não existir nenhum ambiente, crie somente um na raiz com `py -3.12 -m venv .venv` no Windows ou `python3.12 -m venv .venv` no Linux.

Os inicializadores instalam as dependências Python e npm, preparam os modelos e o banco, aguardam a API responder e iniciam o Angular. As portas 8000 e 4200 precisam estar livres. A instalação de dependências e o primeiro download dos modelos exigem internet.

- Front: http://localhost:4200
- API e Swagger: http://localhost:8000/docs

Mantenha o terminal aberto e use **Ctrl+C** para encerrar os servidores iniciados por ele. No Windows, os logs ficam em `backend/.runtime/api.log`, `api-error.log`, `frontend.log` e `frontend-error.log`; os arquivos são renovados a cada inicialização. No Linux, a API registra em `backend/.runtime/api.log` e a saída do Angular aparece no terminal. Credenciais, chaves e modelos continuam dentro de `backend`.

## Estágios do processamento

O fluxo é implementado em [backend/app/biometria.py](backend/app/biometria.py).

| Estágio | Funcionamento no backend | Função principal |
| --- | --- | --- |
| **1. Aquisição** | Recebe de três a cinco quadros RGB enviados pelo cliente, decodifica os bytes e valida formato, dimensões e tamanho da captura. | `sensoriamento()` |
| **2. Pré-processamento** | Converte os pixels para processamento numérico e aplica suavização binomial para calcular a luminância utilizada na análise de qualidade. Os pixels RGB são preservados para a detecção e o reconhecimento. | `pre_processamento()` |
| **3. Segmentação** | Localiza a região facial com YuNet, exige um único rosto e verifica enquadramento, iluminação, contraste, saturação e nitidez. Utiliza cinco pontos faciais para alinhar o rosto em uma imagem de 112 × 112 pixels. | `segmentacao()` |
| **4. Extração de características** | Executa o AuraFace sobre o rosto alinhado e produz um vetor de 512 dimensões, normalizado para a comparação biométrica. | `extracao_caracteristicas()` |
| **5. Classificação e interpretação** | Calcula a distância de cosseno entre a captura e a assinatura cadastrada, aplica o limiar de aceitação e interpreta o resultado para aceitar ou recusar a identidade apresentada. | `classificacao_interpretacao()` |

A função `processar_captura()` coordena o fluxo, verifica a consistência entre os quadros e gera a assinatura e o resumo das etapas. Na autenticação, a classificação compara a captura com o cadastro vinculado às credenciais confirmadas.

## Papel dos modelos

### YuNet: detecção e localização do rosto

O YuNet identifica a presença de faces e retorna a caixa da região facial, a confiança da detecção e cinco pontos de referência: dois olhos, nariz e dois cantos da boca.

O backend utiliza essas informações para selecionar a região facial e realizar seu alinhamento. Capturas sem rosto, com múltiplos rostos ou com enquadramento inadequado são recusadas. A identificação de qual usuário está diante da câmera ocorre na comparação das características extraídas pelo AuraFace.

### AuraFace: extração da assinatura facial

O AuraFace v1 utiliza uma rede de reconhecimento facial baseada em ArcFace/ResNet100. A partir do rosto alinhado, gera um **embedding de 512 dimensões**: uma representação numérica das características faciais utilizada para comparar identidades.

Cada quadro produz um vetor normalizado. O backend verifica a consistência dessas amostras e calcula um vetor agregado para o cadastro. Na validação, também verifica cada quadro contra a assinatura cadastrada, impedindo que apenas a média das amostras determine a aceitação de um quadro divergente.

Os modelos são executados localmente pelo OpenCV e pelo ONNX Runtime. Os arquivos carregados têm tamanho e SHA-256 verificados, e falhas na disponibilidade ou na integridade dos modelos interrompem o processamento biométrico.

## Da assinatura ao armazenamento e à validação

No cadastro, a assinatura reúne a versão do formato, a identificação do algoritmo, a dimensão, o vetor agregado e as amostras dos quadros. Essa estrutura é serializada em JSON, comprimida e cifrada com AES-GCM antes de ser armazenada em um campo BLOB no MySQL.

Na autenticação de um usuário comum, o backend primeiro confirma CPF e senha e emite um desafio temporário vinculado àquele cadastro. Os quadros recebidos na etapa biométrica percorrem o mesmo fluxo de processamento e extração de características. A assinatura armazenada é decifrada e comparada exclusivamente com a captura daquele usuário, em uma **verificação facial 1:1**.

Uma correspondência aceita permite emitir a sessão com o nível do usuário. Capturas incompatíveis são recusadas. O administrador de nível 4 possui o fluxo específico de acesso por CPF e senha, sem validação biométrica.

O resumo retornado pela API apresenta os cinco estágios, as medidas de qualidade e o modelo utilizado, permitindo acompanhar a aplicação do processamento de imagens no projeto.

## Limite do reconhecimento facial

A prova de vida permanece uma verificação adicional ainda pendente. Uma fotografia da própria identidade cadastrada pode ser reconhecida pelo modelo; a comparação de características faciais, por si só, não comprova a presença de uma pessoa viva diante da câmera.
