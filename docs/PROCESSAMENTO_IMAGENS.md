# Processamento de imagens e assinatura biométrica

O núcleo didático está em `app/biometria.py`: as cinco fases são funções explícitas, com operações NumPy implementadas no projeto. Não há download de pesos, detector facial pré-treinado, Haar Cascade, MediaPipe ou serviço externo de reconhecimento.

O método desta primeira versão é uma **comparação de aparência da região facial enquadrada pelo usuário**. A segmentação usa uma elipse fixa e não localiza rostos arbitrários na imagem. A câmera deve mostrar uma pessoa de frente e alinhada à guia. Essa restrição torna as etapas inspecionáveis, mas limita bastante a verificação facial.

## 1. Fluxo completo

Na autenticação, CPF e senha são conferidos antes de liberar a etapa biométrica:

```text
CPF + senha → credenciais aceitas → desafio de uso único (120 segundos)
  → liberação da câmera
  → botão de captura e contagem de 3 segundos
  → lote de quadros RGB
  → sensoriamento
  → pre_processamento
  → segmentacao
  → extracao_caracteristicas
  → assinatura do lote
  → classificacao_interpretacao
  → comparação 1:1 com a assinatura do usuário do desafio
  → face aceita → sessão completa → consulta do nível cadastrado
  → face recusada → nenhuma sessão completa
```

`POST /api/autenticacao/credenciais` recebe apenas CPF e senha. Em caso de sucesso, emite o cookie `HttpOnly` `aps_desafio`. Esse desafio vale 120 segundos e autoriza uma única tentativa, sem conceder acesso ao nível. `POST /api/autenticacao/verificar` recebe somente os quadros e exige esse cookie; o usuário a comparar já está determinado no servidor. A rota de identificação apenas pelo rosto foi removida.

No cadastro, o vetor extraído compõe a assinatura armazenada. Na autenticação, a API extrai uma nova assinatura e compara somente com a assinatura vinculada ao desafio. O nível vem do registro desse usuário, nunca de um valor escolhido pelo navegador durante a autenticação. CPF e senha precisam ser validados novamente após o desafio expirar ou a tentativa ser consumida.

Os níveis `1`, `2` e `3` mantêm o agrupamento previsto na documentação da APS. Nesta entrega não concedem acesso a arquivos, cofre ou outras operações: a página de resultado apenas informa o grupo registrado.

## 2. As cinco fases

| Fase | Função principal | Operação | Resultado |
| --- | --- | --- | --- |
| Sensores / aquisição | `sensoriamento` | Valida dimensões e Base64; transforma bytes RGB em matriz NumPy. | Imagem RGB numérica. |
| Pré-processamento | `pre_processamento` | Converte RGB em luminância e suaviza com filtro binomial 3×3. | Imagem em escala de cinza com ruído reduzido. |
| Segmentação | `segmentacao` | Recorta a guia, avalia qualidade, normaliza a intensidade, redimensiona e define a máscara elíptica. | Região de interesse padronizada, máscara e medidas de qualidade. |
| Extração de características | `extracao_caracteristicas` | Calcula padrões locais, orientações de gradiente e intensidade espacial. | Vetor descritivo de 1.136 componentes. |
| Classificação e interpretação | `classificacao_interpretacao` | Na autenticação, compara a captura com a assinatura do usuário do desafio e aplica o limiar. | Aceite ou rejeição da comparação 1:1, sem inferir permissões por aparência. |

### 2.1. Sensores: captura da câmera

O sensor físico é a câmera do computador. A página obtém o fluxo com `navigator.mediaDevices.getUserMedia()`. Cada captura passa por um `canvas`; `getImageData()` fornece pixels RGBA, dos quais a página conserva R, G e B. [MDN: pixels com getImageData](https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/getImageData).

Na validação, a interface só libera a câmera depois da confirmação de CPF e senha. Ao acionar a captura, exibe três segundos de contagem para permitir o posicionamento. A prévia é espelhada apenas por CSS: o canvas recebe os pixels originais, preservando a orientação das assinaturas anteriores. Nenhuma dessas mudanças altera o descritor ou calibra sua precisão.

O contrato de cada quadro é:

```json
{
  "largura": 320,
  "altura": 240,
  "rgb_base64": "BASE64_DOS_BYTES_RGB"
}
```

O texto acima é uma ilustração do contrato, não uma imagem válida. São três bytes por pixel, na ordem R, G, B, percorrendo linhas de cima para baixo. Um quadro de 320×240 contém 230.400 bytes antes da codificação Base64. O lote contém entre três e cinco quadros com as mesmas dimensões. O módulo aceita largura entre 160 e 640 e altura entre 120 e 480; as páginas de teste usam 320×240. A quantidade exata de bytes deve corresponder às dimensões informadas, sem canal alfa.

Não se usa `toDataURL()`, arquivo PNG, arquivo JPEG, seletor de arquivo nem caminho local de foto. Base64 é apenas uma codificação de transporte: não é criptografia e não certifica a origem dos pixels. Um cliente que imite o contrato pode enviar pixels que não vieram de uma câmera; a API não consegue atestar essa origem por esse formato.

### 2.2. Pré-processamento

O módulo converte cada pixel RGB para luminância aproximada:

```text
Y = 0,299 R + 0,587 G + 0,114 B
```

Em seguida aplica o filtro binomial separável `[1, 2, 1] / 4`, primeiro horizontalmente e depois verticalmente. Isso equivale a uma suavização 3×3. As bordas são refletidas para permitir a operação nas extremidades. A suavização reduz ruído fino antes do cálculo da textura, sem utilizar uma biblioteca de visão computacional.

As medidas de qualidade e a normalização são executadas na fase seguinte, depois de selecionar a região da guia, para que áreas externas ao enquadramento não dominem esses cálculos.

### 2.3. Segmentação guiada

A guia é proporcional ao quadro inteiro:

- Posição do retângulo da elipse: `x = 0,25 × largura`, `y = 0,10 × altura`.
- Tamanho do retângulo: `0,50 × largura` por `0,80 × altura`.
- Centro: `(0,50 × largura, 0,50 × altura)`.
- Região canônica: 96 pixels de largura por 112 de altura.

No quadro de 320×240, o retângulo corresponde a `x=80`, `y=24`, `largura=160`, `altura=192`. A máscara elíptica descarta os cantos desse retângulo. O redimensionamento usa interpolação bilinear implementada no próprio módulo.

Antes da normalização, a função calcula estas medidas sobre a região elíptica da imagem em escala de cinza:

| Medida | Cálculo | Requisito inicial |
| --- | --- | --- |
| Iluminação | Média dos pixels | Entre 35 e 225 na escala 0–255. |
| Contraste | Desvio padrão dos pixels | Pelo menos 14. |
| Foco | Desvio padrão do Laplaciano discreto | Pelo menos 1,5 (experimental). |
| Saturação | Fração de pixels com valor ≤ 8 ou ≥ 247 | No máximo 0,55. |

Esses limites são critérios exploratórios de qualidade, não critérios validados de reconhecimento. A normalização transforma os percentis 2 e 98 da região em limites da escala 0–1, com corte dos valores que ultrapassam essa faixa. Ajuda a lidar com parte das mudanças de iluminação, sem eliminar sombras ou diferenças de câmera.

Qualidade suficiente não confirma uma face: um objeto bem iluminado também pode atender aos requisitos.

Essa é uma segmentação geométrica definida pelo posicionamento do participante. Ela **não detecta** a posição real da cabeça, olhos ou boca; não separa semanticamente pele, cabelo e fundo. Se a pessoa sair da guia ou se houver um objeto dentro dela, a função processará aquela região mesmo assim.

### 2.4. Extração de características

A assinatura usa o algoritmo versionado `aps-lbp59-gradientes-v1`, implementado sem um modelo treinado. Ele combina três componentes:

| Componente | Organização | Dimensões | Peso |
| --- | --- | ---: | ---: |
| Padrões binários locais (LBP) uniformes | 59 classes em cada célula de uma grade 4×4 | 944 | 0,55 |
| Gradientes | 8 orientações em cada célula de uma grade 4×4 | 128 | 0,30 |
| Intensidade relativa espacial | Grade 8×8 | 64 | 0,15 |
| Total | Vetor combinado | 1.136 | 1,00 |

O LBP compara cada pixel com seus oito vizinhos imediatos: um vizinho maior ou igual ao centro gera bit 1; caso contrário, bit 0. Os oito bits formam um código. Padrões com até duas transições circulares entre 0 e 1 recebem classes próprias; os demais compartilham a classe residual, totalizando 59 classes. Pixels cujos vizinhos saem da máscara são excluídos.

Os gradientes descrevem as mudanças na imagem em oito orientações sem sinal, no intervalo de 0 a 180 graus, ponderadas pela magnitude. Cada célula espacial normaliza seu histograma; a concatenação das células mantém o peso do componente.

A distribuição espacial de intensidade acrescenta informação sobre áreas claras e escuras. As médias das células recebem um pequeno deslocamento de `0,05` e são normalizadas. As grades preservam uma noção grosseira de posição, por isso deslocar o rosto altera o resultado.

`processar_captura` aplica as fases 1 a 4 a cada quadro e compara os descritores dentro do lote. Se a maior distância de Hellinger entre dois deles exceder `0,35`, o lote é recusado por inconsistência. Esse limite também é experimental. O vetor final é a média dos descritores aceitos, novamente normalizada. Quadros repetidos podem passar nessa verificação: ela não exige movimento e não demonstra prova de vida.

A estrutura lógica da assinatura é:

```json
{
  "versao": 1,
  "algoritmo": "aps-lbp59-gradientes-v1",
  "dimensao": 1136,
  "vetor": [0.001, 0.002]
}
```

O vetor acima está abreviado. A assinatura real precisa conter todas as 1.136 componentes válidas; não use o exemplo como cadastro. O versionamento permite recusar uma assinatura incompatível em vez de compará-la silenciosamente com outro algoritmo. Uma futura mudança de descritor pode exigir recadastro.

### 2.5. Classificação e interpretação

A distância utilizada é a de Hellinger, aplicada aos vetores normalizados:

```text
d(p, q) = sqrt(sum((sqrt(p[i]) - sqrt(q[i]))²)) / sqrt(2)
```

O resultado fica entre zero e um para distribuições válidas. Quanto menor, mais parecida é a representação. Distância zero significa vetores iguais, não certeza de que duas capturas vieram da mesma pessoa.

Na autenticação atual, existe somente um candidato: a assinatura do usuário associado ao desafio emitido após CPF e senha válidos. A comparação é aceita quando sua distância fica dentro do limiar; valores acima são recusados. A API não busca o rosto mais parecido entre todos os cadastros.

O valor inicial é **limiar 0,20**, configurável por `FACE_THRESHOLD` no `.env`. Trata-se de um parâmetro exploratório, sem calibração em uma população real. Não é uma taxa de erro nem uma probabilidade. Aumentá-lo facilita o aceite e pode aumentar falsos positivos.

A função matemática também admite listas de candidatos e possui uma regra de margem para comparar primeiro e segundo lugares. Essa possibilidade permanece no módulo didático, mas não é usada como fluxo de login: com a verificação 1:1 não existe segundo candidato. A margem não compensa o limiar nem corrige falhas da captura.

## 3. Assinatura, BLOB e criptografia

Os pixels da captura são usados no processamento em memória. A assinatura é o JSON com descritor e metadados. O módulo de segurança serializa esse JSON em UTF-8, comprime os bytes com zlib e criptografa com AES-256-GCM. O envelope binário contém a informação necessária à leitura, incluindo um nonce aleatório de 12 bytes, e é armazenado em `MEDIUMBLOB` no MySQL/MariaDB.

Na leitura, a aplicação autentica e descriptografa o envelope, descomprime os bytes e reconstrói o JSON. O tipo do dado e `biometria_ref`, UUID imutável do cadastro, entram como dados autenticados adicionais (AAD), vinculando o conteúdo à sua finalidade e registro. `usuarios.id` é um inteiro com incremento automático e não substitui esse vínculo criptográfico. `BIOMETRIC_KEY` é a chave de 32 bytes codificada em Base64 URL-safe, gerada por `scripts/configurar.py`.

A migração conserva o UUID antigo em `biometria_ref` e copia os BLOBs sem modificá-los. Assim, a mudança do ID para inteiro não exige gerar novas assinaturas. O plano, a aplicação e os backups dessa migração são descritos no [Guia do XAMPP](GUIA_XAMPP.md).

**BLOB é um tipo de armazenamento, não um método de criptografia.** Serializar JSON para bytes não o torna confidencial. A criptografia é a etapa que protege seu conteúdo; a autenticação do ciphertext permite detectar alterações antes de usar a assinatura.

O uso de BLOB também não garante, por si só, leitura mais rápida que JSON ou texto. O custo depende de tamanho, criptografia e consulta. Neste protótipo o banco não compara vetores criptografados: a aplicação recupera a assinatura vinculada ao desafio, descriptografa seu conteúdo e calcula a distância para a captura. A autenticação atual não varre todos os cadastros.

Não grave senha em texto, assinatura descriptografada ou quadros da câmera nos logs. A aplicação usa Argon2id para a senha; a biometria precisa de criptografia reversível porque a aplicação compara seu vetor. O CPF também é criptografado e recebe um índice HMAC para busca e controle de duplicidade. A chave de criptografia deve ficar separada do banco e fora dos arquivos públicos. O banco comprometido, isoladamente, não contém a chave; o acesso simultâneo ao banco e ao `.env` remove essa separação.

## 4. Protocolo de teste funcional

Use primeiro a execução descrita em [Guia do XAMPP](GUIA_XAMPP.md), mesmo se decidir testar apenas a porta 8000.

1. Cadastre uma pessoa em iluminação frontal estável, sem girar a cabeça e com o rosto dentro da guia. Aguarde a contagem de três segundos ao acionar o cadastro.
2. Na validação, envie primeiro CPF e senha. Confirme que a câmera só é liberada após essas credenciais serem aceitas e que o desafio sozinho não permite consultar o nível.
3. Faça outra captura da mesma pessoa, após a contagem, com enquadramento semelhante. Registre se a API aceitou ou rejeitou a face.
4. Em um ensaio combinado com os participantes, valide as credenciais do cadastro de teste e apresente outra pessoa à câmera para avaliar a comparação impostora. A etapa de senha e a etapa biométrica devem ter resultados registrados separadamente.
5. Verifique que o nível exibido corresponde ao cadastro autenticado. Teste também desafio expirado ou reutilizado: uma nova tentativa exige validar novamente CPF e senha.
6. Teste câmera sem permissão, quadro escuro, quadro excessivamente claro, desfoco, CPF duplicado, banco indisponível e assinatura corrompida em ambiente de teste.
7. Confira os registros de evento sem expor senha, CPF completo, imagem ou vetor biométrico nos relatórios.

Não altere o limiar após cada erro apenas para fazer a demonstração passar. Registre a condição, o comportamento e a distância quando disponível no ambiente de avaliação. Testes automatizados com matrizes sintéticas verificam operações matemáticas e validação; não medem reconhecimento de pessoas.

## 5. Como avaliar a biometria com pessoas reais

Separe avaliação biométrica de teste de API. Um cadastro salvo e uma resposta HTTP correta só demonstram que o fluxo de software executou.

### Organização dos dados

- Obtenha a participação voluntária das pessoas envolvidas e explique o uso experimental da assinatura.
- Faça sessões de cadastro e de consulta separadas. Não reutilize os mesmos quadros nos dois lados.
- Reserve um conjunto para escolher o limiar e outro, ainda não examinado, para medir o resultado final.
- Inclua comparações genuínas e impostoras com uma identidade de teste declarada. Pessoas sem cadastro podem participar das comparações impostoras com as credenciais do cadastro experimental.
- Registre condições relevantes: câmera, distância, luz, óculos, pequenos desvios de pose e passagem do tempo.
- Use identificadores de avaliação em vez de CPF no relatório.

### Medidas

Na verificação de uma identidade declarada, conte comparações genuínas (mesma pessoa) e impostoras (pessoas diferentes):

```text
FAR = falsos aceites / tentativas impostoras
FRR = falsas rejeições / tentativas genuínas
```

Conte essas taxas somente entre tentativas que chegaram à comparação biométrica; uma senha recusada não é uma rejeição facial. Registre à parte falhas de credenciais, expiração do desafio, problemas de aquisição e erros de infraestrutura. Essa separação permite saber se a falha veio da captura, do descritor ou de outra etapa do fluxo.

Para cada limiar, registre contagens e taxas no conjunto de calibração. Escolha o parâmetro conforme o objetivo do experimento e congele a escolha antes de executar o conjunto final. Informe sempre o número de participantes, tentativas e condições junto com as taxas. Zero erros em poucas tentativas não comprova erro zero na população.

Um relatório simples pode conter:

| Condição | Genuínas | Falsas rejeições | Impostoras | Falsos aceites | Limiar |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mesma câmera e luz | preencher | preencher | preencher | preencher | 0,20 |
| Luz diferente | preencher | preencher | preencher | preencher | 0,20 |
| Outra sessão | preencher | preencher | preencher | preencher | 0,20 |

## 6. Limites desta versão

- Não há detector facial automático nem garantia de que os pixels representam uma face.
- Não há prova de vida: fotografia, tela ou repetição de quadros podem enganar o fluxo.
- As medidas de qualidade não são mecanismo contra falsificação.
- O descritor é sensível a pose, escala, enquadramento, iluminação, câmera, fundo e aparência.
- Não há precisão biométrica comprovada; os parâmetros iniciais precisam de avaliação experimental.
- Criptografar a assinatura no banco protege o armazenamento, mas não corrige falsos aceites do algoritmo.
- Os níveis são metadados de cadastro. Uma futura operação protegida deverá conferir a sessão e suas permissões no servidor; exibir a página de nível não constitui autorização dessa operação.

O cenário de cofre da documentação acadêmica serve como motivação. Este protótipo demonstra o processamento e a integração; sua saída não deve ser apresentada como um controle de segurança já validado para aquele cenário.
