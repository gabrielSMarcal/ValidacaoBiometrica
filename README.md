# APS — Processamento de imagens e reconhecimento facial

Autenticação com CPF, senha e verificação facial 1:1. O frontend usa Angular; o backend usa FastAPI, MySQL, YuNet e AuraFace com ONNX Runtime. TensorFlow e Keras não fazem parte da execução atual.

## Executar no Windows

1. Inicie o MySQL e confira a configuração em `backend/.env`.
2. Tenha Python 3.12 completo e Node.js/npm compatível com Angular 22 instalados, com as portas 8000 e 4200 disponíveis.
3. Execute na raiz:

```powershell
.\iniciar.bat
```

O pacote inclui a `.venv`, um Python 3.12.10 para Windows de 64 bits e os dois modelos. O inicializador Windows ajusta o caminho desse Python se a pasta do projeto mudar. Ambos os inicializadores reutilizam a `.venv` funcional da raiz ou de `backend`; quando não houver ambiente e a pasta `.venv` da raiz estiver ausente, criam-na automaticamente usando o Python 3.12 instalado na máquina. Um ambiente existente inválido é preservado, com uma mensagem para revisão.

Depois, instalam as dependências, preparam os modelos e o banco, aguardam a API responder e abrem automaticamente a página no navegador após a compilação do frontend. A instalação Python/npm, o download de modelos ausentes e os recursos MediaPipe carregados pelo navegador exigem internet.

- Aplicação: http://localhost:4200
- API e Swagger: http://localhost:8000/docs

Mantenha o terminal aberto e use **Ctrl+C** para encerrar os servidores. Os logs ficam em `backend/.runtime/` e são renovados a cada inicialização.

No Linux, execute `bash ./iniciar.sh`. O Python 3.12 deve estar disponível como `python3.12`, `python3` ou `python`, com os módulos `venv` e `ensurepip`; o script cria a `.venv` automaticamente quando ela não existe. Um ambiente Windows não é compatível com Linux: mantenha a `.venv` própria do sistema ou mova a cópia Windows para outro local antes da primeira execução.

O MySQL/MariaDB precisa estar instalado e ativo antes da execução; os scripts não instalam o servidor de banco. Copie o `.env` fornecido pela equipe para `backend/.env`, com conexão e administrador inicial configurados. O Node deve atender à faixa do Angular instalado: `^22.22.3 || ^24.15.0 || >=26.0.0`. No Windows, o criador do ambiente procura primeiro `py -3.12` e depois um Python 3.12 disponível no `PATH`.

## Configuração do banco e do administrador

Arquivos `.env`, chaves e bancos são locais e não acompanham o ZIP. Se já existe uma configuração da equipe, preserve-a. Em uma instalação nova no Windows, prepare o ambiente antes de usar Python diretamente:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File backend\scripts\iniciar_servidores.ps1 -PrepararPython
.\.venv\Scripts\python.exe backend\scripts\configurar.py
```

O configurador cria `backend/.env` sem sobrescrever um arquivo existente. Ajuste:

| Variável | Finalidade |
| --- | --- |
| `DB_HOST`, `DB_PORT` | Endereço e porta do MySQL; padrões `127.0.0.1` e `3306`. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Banco e credenciais de conexão. |
| `ADMIN_CPF` | CPF válido do administrador inicial. |
| `ADMIN_PASSWORD_HASH` | Hash Argon2id da senha inicial. |
| `BIOMETRIC_KEY` | Chave original de 32 bytes em base64 para os dados cifrados. |
| `ALLOWED_ORIGINS` | Origens web autorizadas; os padrões incluem `http://localhost:4200`. |

Para gerar o hash da senha inicial, execute e cole o resultado em `ADMIN_PASSWORD_HASH`:

```powershell
.\.venv\Scripts\python.exe -c "from getpass import getpass; from argon2 import PasswordHasher; print(PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash(getpass('Senha inicial do administrador: ')))"
```

O inicializador cria o banco e as tabelas quando as permissões MySQL permitem; `backend/sql/criar_banco.sql` é a alternativa manual. Um administrador existente mantém sua senha. Alterações conhecidas de estrutura preservam os cadastros existentes.

Uma cópia de um banco existente exige a **mesma chave biométrica**. Quando não houver `BIOMETRIC_KEY` no ambiente ou no `.env`, a chave fica em `backend/.runtime/biometric.key`; preserve esse arquivo ao transferir o banco. Assinaturas de algoritmos anteriores exigem recadastro biométrico.

## Organização do código

`backend/app/main.py` concentra a API, configuração, validação das entradas, persistência, criptografia, preparação dos modelos e coordenação da captura. `backend/app/inicializar.py` é o comando de preparação do banco.

As cinco fases ficam reunidas na pasta `backend/app/processamento/`:

| Fase | Arquivo | Operação |
| --- | --- | --- |
| 1. Aquisição | `sensoriamento.py` | Valida dimensões e decodifica os bytes RGB. |
| 2. Pré-processamento | `pre_processamento.py` | Aplica suavização binomial e calcula a luminância. |
| 3. Segmentação | `segmentacao.py` | Detecta um rosto, confere qualidade e alinha cinco pontos faciais em 112 × 112 pixels. |
| 4. Extração de características | `extracao_caracteristicas.py` | Produz e normaliza o vetor AuraFace de 512 dimensões. |
| 5. Classificação/interpretação | `classificacao_interpretacao.py` | Compara assinaturas por distância de cosseno e aplica os limites de aceitação. |

O cadastro exige três posições: **frente → sua direita → sua esquerda**. O login recebe três quadros diretos. O servidor verifica rosto único, qualidade e consistência entre os quadros; o cadastro também exige movimento e recusa imagens repetidas.

Os modelos em `backend/.runtime/modelos` são preservados com tamanho e SHA-256 verificados:

| Modelo | Arquivo | Tamanho |
| --- | --- | --- |
| YuNet | `face_detection_yunet_2023mar.onnx` | 232.589 bytes |
| AuraFace | `glintr100.onnx` | 260.694.151 bytes |

Os pesos não foram convertidos ou reduzidos. Os limites de comparação permanecem em `0.30`, margem `0.03`, consistência `0.25` e foco mínimo `1.5`. A assinatura mantém versão 3 e algoritmo `auraface-v1-arcface-r100-yunet-112-v3`.

Durante a preparação, o terminal informa o tamanho de cada modelo. Se precisar baixá-lo, mostra os MB recebidos, o total e o percentual de progresso, com aviso de que o download pode demorar. Arquivos já instalados e íntegros são reutilizados; a instalação só é confirmada após a verificação de integridade.

## Endpoints preservados

| Método | Rota | Uso |
| --- | --- | --- |
| `GET` | `/api/saude` | Saúde do banco. |
| `POST` | `/api/usuarios` | Cadastro administrativo. |
| `GET` | `/api/usuarios` | Lista administrativa. |
| `PATCH` | `/api/usuarios/{id}` | Edição administrativa. |
| `PUT` | `/api/usuarios/{id}/biometria` | Recadastro biométrico administrativo. |
| `DELETE` | `/api/usuarios/{id}` | Exclusão administrativa. |
| `POST` | `/api/autenticacao/credenciais` | Confirma CPF e senha. |
| `POST` | `/api/autenticacao/verificar` | Verificação facial vinculada ao desafio. |
| `GET` | `/api/sessao` | Consulta da sessão. |
| `POST` | `/api/sair` | Revoga sessão e desafio. |

As chamadas preservam os cookies `HttpOnly`. O desafio biométrico dura 120 segundos; a sessão dura 15 minutos por padrão. O administrador de nível 4 entra com CPF e senha e gerencia usuários de níveis 1 a 3. Os formatos das requisições e respostas permanecem no Swagger.

Os quadros são processados em memória. CPF e assinatura são cifrados com AES-GCM; senhas usam Argon2id e tokens são armazenados como hashes. A comparação facial e a sequência de movimento não constituem prova de vida.

## Gerar o arquivo de entrega

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\empacotar_projeto.ps1
```

O resultado fica em `.runtime/entrega/APS-Leitura-Facial.zip`. O script inclui código, documentação, `.venv` e modelos; exclui testes da aplicação, caches, `node_modules`, builds, logs e arquivos privados. Confere a integridade dos modelos e recusa um ZIP acima de **500.000.000 bytes**. O projeto local mantém seus arquivos de configuração e as chaves.
