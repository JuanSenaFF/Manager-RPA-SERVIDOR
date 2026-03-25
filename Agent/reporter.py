import asyncio
import logging
import os
import socket
from datetime import datetime

import httpx
from dotenv import load_dotenv

from controller import verificar_processos_gerenciados, carregar_scripts, _norm_name

load_dotenv()

MANAGER_URL   = os.getenv("MANAGER_URL", "http://localhost:5000/agents/report")
# O AGENT_ID deve ser apenas o hostname da máquina (ex: JUANO-LOCAL, BRTDTBGS0031SL)
AGENT_ID      = os.getenv("AGENT_ID", socket.gethostname())
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "10"))

# Usuário Windows logado — usado como o nome do perfil
USERNAME = os.getlogin()

logger = logging.getLogger(__name__)


def _montar_payload(agent_port: int) -> dict:
    """
    Monta o payload de heartbeat no formato de perfis.

    Lógica:
    - O Agent roda sob um único usuário (USERNAME), que é o perfil ativo.
    - Os scripts gerenciados são distribuídos como 'slots' desse perfil:
      cada script ativo ocupa um slot (1 RPA por perfil por vez).
    - O Orquestrador recebe uma lista de perfis, cada um com o RPA ativo ou None.
    """
    scripts = carregar_scripts()
    ativos  = verificar_processos_gerenciados()

    # Mapeia nome_arquivo → {pid, nome_rpa}
    nomes_ativos: dict[str, dict] = {}
    for p in ativos:
        for s in scripts:
            if _norm_name(s["path"]) == p["nome_arquivo"]:
                nomes_ativos[p["nome_arquivo"]] = {"pid": p["pid"], "nome_rpa": s["nome"]}
                break

    # Constrói a lista de perfis/slots.
    # Cada script gerenciado vira um "slot" do perfil logado.
    # Ex: se há 3 scripts e apenas 1 ativo → 1 slot rodando + 2 livres
    perfis = []
    for s in scripts:
        nome_arq = _norm_name(s["path"])
        ativo    = nomes_ativos.get(nome_arq)
        perfis.append({
            "usuario":  USERNAME,
            "slot":     s["nome"],          # identificador único do slot (nome do script)
            "rpa_ativo": s["nome"] if ativo else None,
            "status":   "rodando" if ativo else "livre",
            "pid":      ativo["pid"] if ativo else None,
        })

    return {
        "agent_id":  AGENT_ID,
        "agent_url": f"http://127.0.0.1:{agent_port}",
        "timestamp": datetime.now().isoformat(),
        "perfis":    perfis,
    }


async def iniciar_reporter(agent_port: int):
    """
    Loop assíncrono que envia o status atual ao Manager central
    a cada HEARTBEAT_INTERVAL segundos.
    """
    logger.info(
        f"Reporter iniciado → {MANAGER_URL} | "
        f"Intervalo: {HEARTBEAT_INTERVAL}s | Agent: {AGENT_ID} ({USERNAME}) | Porta: {agent_port}"
    )

    async with httpx.AsyncClient(timeout=5) as client:
        while True:
            try:
                payload  = _montar_payload(agent_port)
                response = await client.post(MANAGER_URL, json=payload)
                logger.info(f"Heartbeat enviado → HTTP {response.status_code}")
            except httpx.ConnectError:
                logger.warning("Manager central indisponível. Tentando novamente...")
            except Exception as e:
                logger.error(f"Erro no reporter: {e}")

            await asyncio.sleep(HEARTBEAT_INTERVAL)

