"""
Script de inicialização do SisPatrimônio Pro.
Executa o servidor FastAPI com Uvicorn.
"""

import uvicorn
from app.config import APP_HOST, APP_PORT, APP_NAME
from app.database import init_db

if __name__ == "__main__":
    print(f"-> Inicializando banco de dados do {APP_NAME}...")
    init_db()
    
    print("=" * 60)
    print(f"[OK] {APP_NAME} iniciado com sucesso!")
    print(f"[>>] Interface Web: http://{APP_HOST}:{APP_PORT}")
    print(f"[>>] Swagger API Docs: http://{APP_HOST}:{APP_PORT}/docs")
    print("=" * 60)

    uvicorn.run(
        "app.main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=False
    )
