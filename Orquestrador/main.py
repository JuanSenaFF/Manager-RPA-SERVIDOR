import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

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

app = Flask(__name__)
# Habilita CORS para o dashboard web conseguir fazer requisições
CORS(app)

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
            ts = ts.astimezone()
        agora = datetime.now(timezone.utc)
        return (agora - ts).total_seconds()
    except Exception:
        return float("inf")

# ---------------------------------------------------------------------------
# Rotas Flask
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    """Serve o dashboard web central do Orquestrador."""
    return send_file(Path(__file__).parent / "dashboard.html")

@app.route("/agents/report", methods=["POST"])
def receive_report():
    """Endpoint chamado pelo reporter.py de cada Agent."""
    data = request.json
    if not data:
        return jsonify({"detail": "Payload inválido"}), 400

    agent_id  = data.get("agent_id")
    agent_url = data.get("agent_url")
    timestamp = data.get("timestamp")
    perfis    = data.get("perfis", [])

    if not agent_id or not agent_url:
        return jsonify({"detail": "agent_id e agent_url são obrigatórios"}), 400

    slots_ocupados = sum(1 for p in perfis if p.get("status") == "rodando")

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

    return jsonify({"mensagem": f"Heartbeat de {agent_id} recebido com sucesso."})

@app.route("/status", methods=["GET"])
def get_consolidated_status():
    """Retorna o estado agrupado para o frontend do Orquestrador."""
    for agent_id, info in agents_state.items():
        if _segundos_desde(info.get("last_seen")) > OFFLINE_TIMEOUT:
            info["status"] = "offline"
            # Marca todos os perfis como offline
            for p in info.get("perfis", []):
                p["status"] = "offline"
                p["rpa_ativo"] = None
                p["pid"] = None
            info["slots_ocupados"] = 0

    return jsonify({"agents": agents_state})

@app.route("/agents/<agent_id>/scripts/<nome>/start", methods=["POST"])
def proxy_start_script(agent_id, nome):
    """Encaminha o comando de START para a API do Agent correspondente."""
    agent = agents_state.get(agent_id)
    if not agent:
        return jsonify({"detail": f"Agent '{agent_id}' não encontrado."}), 404

    if not agent.get("agent_url"):
        return jsonify({"detail": f"O Agent '{agent_id}' ainda não registrou seu IP."}), 503

    url = f"{agent['agent_url']}/scripts/{nome}/start"

    try:
        response = requests.post(url, timeout=10.0)
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({"detail": response.json().get("detail", "Erro no Agent")}), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"detail": f"Não foi possível conectar ao Agent {agent_id}"}), 503

@app.route("/agents/<agent_id>/scripts/<nome>/stop", methods=["DELETE"])
def proxy_stop_script(agent_id, nome):
    """Encaminha o comando de STOP para a API do Agent correspondente."""
    agent = agents_state.get(agent_id)
    if not agent:
        return jsonify({"detail": f"Agent '{agent_id}' não encontrado."}), 404

    if not agent.get("agent_url"):
        return jsonify({"detail": f"O Agent '{agent_id}' ainda não registrou seu IP."}), 503

    url = f"{agent['agent_url']}/scripts/{nome}/stop"

    try:
        response = requests.delete(url, timeout=10.0)
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({"detail": response.json().get("detail", "Erro no Agent")}), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"detail": f"Não foi possível conectar ao Agent {agent_id}"}), 503

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
