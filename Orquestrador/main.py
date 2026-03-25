import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ---------------------------------------------------------------------------
# Carrega a topologia de infraestrutura do infra.yaml
# ---------------------------------------------------------------------------
_INFRA_PATH = Path(__file__).parent.parent / "infra.yaml"

def _carregar_infra() -> dict:
    """Lê o infra.yaml e retorna o conteúdo parseado."""
    with open(_INFRA_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def _build_initial_state(infra: dict) -> dict:
    """
    Monta o estado inicial dos agents a partir do infra.yaml.
    Cada servidor começa como 'offline' com slots 'livre' para cada perfil.
    """
    state = {}
    for srv in infra.get("servidores", []):
        host = srv["host"]
        perfis_cfg = srv.get("perfis", [])
        state[host] = {
            "agent_url": None,
            "last_seen": None,
            "status": "offline",
            "ambiente": srv.get("ambiente", "producao"),
            "capacidade_maxima": srv.get("capacidade_maxima", len(perfis_cfg)),
            "slots_ocupados": 0,
            "perfis": [
                {
                    "usuario": u,
                    "slot": None,
                    "rpa_ativo": None,
                    "status": "offline",
                    "pid": None,
                }
                for u in perfis_cfg
            ],
        }
    return state

_infra = _carregar_infra()

app = FastAPI(
    title="Manager RPA — Orquestrador",
    description="Painel central que recebe heartbeats dos Agents e envia comandos de controle.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estado em memória — pré-populado com todos os servidores do infra.yaml
agents_state: dict = _build_initial_state(_infra)

# Timeout (segundos) sem heartbeat para marcar agent como offline
OFFLINE_TIMEOUT = 45


def _segundos_desde(iso_str: str | None) -> float:
    """Retorna quantos segundos se passaram desde um timestamp ISO 8601."""
    if not iso_str:
        return float("inf")
    try:
        ts = datetime.fromisoformat(iso_str)
        if ts.tzinfo is None:
            # Assume que a string naive veio do fuso local da máquina (ex: -03:00)
            ts = ts.astimezone()
        agora = datetime.now(timezone.utc)
        return (agora - ts).total_seconds()
    except Exception:
        return float("inf")


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def dashboard():
    """Serve o dashboard web central do Orquestrador."""
    return FileResponse(Path(__file__).parent / "dashboard.html")


@app.post("/agents/report", summary="Recebe heartbeat de um Agent")
async def receive_report(request: Request):
    """
    Endpoint chamado pelo reporter.py de cada Agent.
    Formato esperado do payload:
    {
        "agent_id": "BRTDTBGS0031SL",
        "agent_url": "http://10.0.0.1:8000",
        "timestamp": "2026-03-24T20:00:00",
        "perfis": [
            { "usuario": "SVC_OI_CEEX", "slot": "cancelamento_next",
              "rpa_ativo": "cancelamento_next", "status": "rodando", "pid": 1234 },
            ...
        ]
    }
    """
    data      = await request.json()
    agent_id  = data.get("agent_id")
    agent_url = data.get("agent_url")
    timestamp = data.get("timestamp")
    perfis    = data.get("perfis", [])

    if not agent_id or not agent_url:
        raise HTTPException(status_code=400, detail="agent_id e agent_url são obrigatórios")

    slots_ocupados = sum(1 for p in perfis if p.get("status") == "rodando")

    # Se o agent não está cadastrado no infra.yaml, adiciona dinamicamente
    if agent_id not in agents_state:
        agents_state[agent_id] = {
            "agent_url": agent_url,
            "last_seen": timestamp,
            "status": "online",
            "ambiente": "desconhecido",
            "capacidade_maxima": len(perfis),
            "slots_ocupados": slots_ocupados,
            "perfis": perfis,
        }
    else:
        agents_state[agent_id].update({
            "agent_url": agent_url,
            "last_seen": timestamp,
            "status": "online",
            "slots_ocupados": slots_ocupados,
            "perfis": perfis,
        })

    return {"mensagem": f"Heartbeat de {agent_id} recebido com sucesso."}


@app.get("/status", summary="Visualiza o status consolidado de todos os Agents")
def get_consolidated_status():
    """
    Retorna o estado agrupado para o frontend do Orquestrador.
    Agents sem heartbeat por mais de OFFLINE_TIMEOUT segundos são marcados offline.
    """
    for agent_id, info in agents_state.items():
        if _segundos_desde(info.get("last_seen")) > OFFLINE_TIMEOUT:
            info["status"] = "offline"
            # Marca todos os perfis como offline
            for p in info.get("perfis", []):
                p["status"] = "offline"
                p["rpa_ativo"] = None
                p["pid"] = None
            info["slots_ocupados"] = 0

    return {"agents": agents_state}


@app.post("/agents/{agent_id}/scripts/{nome}/start")
async def proxy_start_script(agent_id: str, nome: str):
    """Encaminha o comando de START para a API do Agent correspondente."""
    agent = agents_state.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' não encontrado.")

    if not agent.get("agent_url"):
        raise HTTPException(status_code=503, detail=f"O Agent '{agent_id}' ainda não registrou seu IP (Offline).")

    url = f"{agent['agent_url']}/scripts/{nome}/start"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, timeout=10.0)
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.json().get("detail", "Erro no Agent")
                )
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail=f"Não foi possível conectar ao Agent {agent_id} ({agent['agent_url']})"
            )


@app.delete("/agents/{agent_id}/scripts/{nome}/stop")
async def proxy_stop_script(agent_id: str, nome: str):
    """Encaminha o comando de STOP para a API do Agent correspondente."""
    agent = agents_state.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' não encontrado.")

    if not agent.get("agent_url"):
        raise HTTPException(status_code=503, detail=f"O Agent '{agent_id}' ainda não registrou seu IP (Offline).")

    url = f"{agent['agent_url']}/scripts/{nome}/stop"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(url, timeout=10.0)
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.json().get("detail", "Erro no Agent")
                )
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail=f"Não foi possível conectar ao Agent {agent_id} ({agent['agent_url']})"
            )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5500, reload=False)

