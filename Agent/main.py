import asyncio
import logging
import threading
from flask import Flask, jsonify, request
from flask_cors import CORS

from controller import (
    carregar_scripts,
    verificar_processos_gerenciados,
    iniciar_processo,
    matar_processo,
    _norm_name,
)
from reporter import iniciar_reporter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

app = Flask(__name__)
# Configura o CORS para permitir todas as origens
CORS(app)

@app.route("/status", methods=["GET"])
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

    return jsonify({"scripts": resultado})


@app.route("/scripts/<nome>/start", methods=["POST"])
def start_script(nome):
    """
    Inicia um script gerenciado pelo nome definido no YAML.
    """
    scripts = carregar_scripts()
    alvo = next((s for s in scripts if s["nome"] == nome), None)

    if not alvo:
        return jsonify({"detail": f"Script '{nome}' não encontrado no YAML."}), 404

    sucesso = iniciar_processo(alvo["path"])
    if not sucesso:
        return jsonify({"detail": f"'{nome}' já está em execução ou não pôde ser iniciado."}), 409

    return jsonify({"mensagem": f"✅ '{nome}' iniciado com sucesso."})


@app.route("/scripts/<nome>/stop", methods=["DELETE"])
def stop_script(nome):
    """
    Encerra um script gerenciado buscando seu nome oficial no YAML.
    """
    scripts = carregar_scripts()
    alvo = next((s for s in scripts if s["nome"] == nome), None)

    if not alvo:
        return jsonify({"detail": f"Script '{nome}' não encontrado no YAML."}), 404

    nome_arquivo = _norm_name(alvo["path"])
    sucesso = matar_processo(nome_arquivo)

    if not sucesso:
        return jsonify({"detail": f"'{nome}' não está em execução ou não é gerenciado."}), 404

    return jsonify({"mensagem": f"✅ '{nome}' encerrado com sucesso."})


def _run_reporter_in_thread(port: int):
    """
    Função que será rodada em uma thread separada para manter o event loop
    assíncrono do reporter ativo em paralelo ao Flask, que é síncrono.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(iniciar_reporter(port))
    except Exception as e:
        logging.error(f"Erro na thread do reporter: {e}")
    finally:
        loop.close()


if __name__ == "__main__":
    import socket

    def buscar_porta_livre(inicio=8000, fim=8050):
        """Busca a primeira porta TCP livre no intervalo especificado."""
        for p in range(inicio, fim + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', p)) != 0:
                    return p
        return 8000

    porta_livre = buscar_porta_livre()
    app.config['PORT'] = porta_livre
    
    # Inicia a thread responsável pelo heartbeat
    reporter_thread = threading.Thread(
        target=_run_reporter_in_thread,
        args=(porta_livre,),
        daemon=True
    )
    reporter_thread.start()
    
    # Roda o servidor Flask. 
    app.run(host="0.0.0.0", port=porta_livre, debug=False, use_reloader=False)
