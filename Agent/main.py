import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from controller import (
    carregar_scripts,
    verificar_processos_gerenciados,
    iniciar_processo,
    matar_processo,
    _norm_name,
)
from reporter import iniciar_reporter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # O app.state.port deve ser preenchido antes de instanciar o reporter
    port = getattr(app.state, 'port', 8000)
    task = asyncio.create_task(iniciar_reporter(port))
    yield
    task.cancel()


app = FastAPI(
    title="Manager RPA — Mini Agent",
    description="Agent local que expõe e gerencia scripts RPA via API.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/status", summary="Status de todos os scripts gerenciados")
def get_status():
    """
    Retorna todos os scripts do YAML com seu status atual (ativo/inativo).
    """
    scripts = carregar_scripts()
    ativos = verificar_processos_gerenciados()
    nomes_ativos = {p["nome_arquivo"]: p["pid"] for p in ativos}

    resultado = []
    for s in scripts:
        nome = _norm_name(s["path"])
        resultado.append({
            "nome": s["nome"],
            "arquivo": nome,
            "path": s["path"],
            "status": "ativo" if nome in nomes_ativos else "inativo",
            "pid": nomes_ativos.get(nome),
        })

    return {"scripts": resultado}


@app.post("/scripts/{nome}/start", summary="Inicia um script pelo nome")
def start_script(nome: str):
    """
    Inicia um script gerenciado pelo nome definido no YAML.
    """
    scripts = carregar_scripts()
    alvo = next((s for s in scripts if s["nome"] == nome), None)

    if not alvo:
        raise HTTPException(status_code=404, detail=f"Script '{nome}' não encontrado no YAML.")

    sucesso = iniciar_processo(alvo["path"])
    if not sucesso:
        raise HTTPException(status_code=409, detail=f"'{nome}' já está em execução ou não pôde ser iniciado.")

    return {"mensagem": f"✅ '{nome}' iniciado com sucesso."}


@app.delete("/scripts/{nome}/stop", summary="Encerra um script pelo nome")
def stop_script(nome: str):
    """
    Encerra um script gerenciado buscando seu nome oficial no YAML.
    """
    scripts = carregar_scripts()
    alvo = next((s for s in scripts if s["nome"] == nome), None)

    if not alvo:
        raise HTTPException(status_code=404, detail=f"Script '{nome}' não encontrado no YAML.")

    nome_arquivo = _norm_name(alvo["path"])
    sucesso = matar_processo(nome_arquivo)

    if not sucesso:
        raise HTTPException(status_code=404, detail=f"'{nome}' não está em execução ou não é gerenciado.")

    return {"mensagem": f"✅ '{nome}' encerrado com sucesso."}


if __name__ == "__main__":
    import uvicorn
    import socket

    def buscar_porta_livre(inicio=8000, fim=8050):
        """Busca a primeira porta TCP livre no intervalo especificado."""
        for p in range(inicio, fim + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', p)) != 0:
                    return p
        return 8000

    porta_livre = buscar_porta_livre()
    app.state.port = porta_livre
    
    uvicorn.run("main:app", host="0.0.0.0", port=porta_livre, reload=False)
