# Backend

Consulte o [README do projeto](../README.md) para instalação, configuração do `.env`, organização das cinco fases, API e geração do ZIP de entrega.

Após clonar o repositório, instale Python 3.12 com `pip` e `venv`, Node.js 22 (versão 22.22.3 ou superior da linha 22) com npm e MySQL. Mantenha o MySQL ativo e coloque o `.env` disponibilizado pela equipe em `backend/.env`, com a conexão e o administrador inicial configurados.

Não é necessário criar um perfil “Database Connection” em um cliente gráfico para executar o projeto. A API se conecta diretamente ao MySQL Server com os dados de `backend/.env`. O servidor e o usuário MySQL com as permissões necessárias devem estar preparados antes de executar o inicializador; consulte a [configuração do banco no README principal](../README.md#configuração-do-banco-e-do-administrador). Os scripts não criam perfis nos clientes gráficos.

Na raiz do projeto, execute `.\iniciar.bat` no Windows ou `bash ./iniciar.sh` no Linux. É necessário acesso à internet. O inicializador cria a `.venv`, instala as dependências de `requirements.txt` e do frontend, baixa os modelos ausentes para `backend/.runtime/modelos`, prepara o banco e inicia a API e o frontend. As pastas `.venv`, `.runtime` e `node_modules` são criadas localmente durante a preparação.

Após essa preparação, para iniciar somente a API a partir desta pasta:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Use um único worker, pois o controle de tentativas por IP é mantido em memória por processo.
