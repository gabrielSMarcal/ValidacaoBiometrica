# Frontend

Frontend Angular do projeto APS de reconhecimento facial. Consulte os detalhes de instalação e execução no [README principal](../../README.md).

Para executar o projeto completo após o clone, instale Python 3.12 com `pip` e `venv`, Node.js 22 (versão 22.22.3 ou superior da linha 22) com npm e MySQL. Mantenha o MySQL ativo e coloque o `.env` disponibilizado pela equipe em `backend/.env`, com a conexão e o administrador inicial configurados.

Com acesso à internet, execute `.\iniciar.bat` no Windows ou `bash ./iniciar.sh` no Linux, a partir da raiz do repositório. O inicializador cria a `.venv`, instala as dependências Python e npm, baixa os modelos ausentes para `backend/.runtime/modelos`, prepara o banco e inicia o backend e o frontend. As pastas `.venv`, `.runtime` e `node_modules` são criadas localmente durante a preparação.

Após o preparo, a aplicação fica disponível em http://localhost:4200.
