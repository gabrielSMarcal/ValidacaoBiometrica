# Backend

Consulte o [README do projeto](../README.md) para execução, configuração, organização das cinco fases, API e geração do ZIP de entrega.

Com o ambiente e o MySQL preparados, a execução manual a partir desta pasta é:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Use um único worker, pois o controle de tentativas por IP é mantido em memória por processo.
