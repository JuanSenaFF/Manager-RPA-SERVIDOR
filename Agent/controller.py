import logging
import subprocess
import sys
import os
import psutil
from pathlib import Path
from utils.ler_yaml import carregar_scripts

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _norm_name(caminho: str) -> str:
    """Retorna apenas o nome do arquivo a partir de um caminho."""
    return Path(caminho).name


def listar_processos_python() -> list[dict]:
    """Identifica todos os arquivos Python em execução na máquina."""
    processos_python = []

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline:
                    for arg in cmdline:
                        if arg.endswith('.py'):
                            processos_python.append({
                                'pid': proc.info['pid'],
                                'nome_processo': proc.info['name'],
                                'arquivo': arg,
                                'nome_arquivo': os.path.basename(arg),
                                'caminho_completo': os.path.abspath(arg) if os.path.exists(arg) else arg
                            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return processos_python


def verificar_processos_gerenciados() -> list[dict]:
    """
    Cruza os processos Python em execução com a lista do scripts.yaml.
    Retorna apenas os processos que estão sendo gerenciados pelo Manager RPA.
    """
    scripts_gerenciados = carregar_scripts()
    nomes_gerenciados = {_norm_name(s['path']) for s in scripts_gerenciados}
    processos_ativos = listar_processos_python()

    return [p for p in processos_ativos if p['nome_arquivo'] in nomes_gerenciados]


def iniciar_processo(path_script: str) -> bool:
    """
    Inicia um script Python como processo independente.

    Args:
        path_script: caminho completo do script (ex: do campo 'path' do YAML)

    Returns:
        True se iniciado com sucesso, False caso contrário.
    """
    nome = _norm_name(path_script)

    # Verifica se já está rodando
    ativos = verificar_processos_gerenciados()
    if any(p['nome_arquivo'] == nome for p in ativos):
        logging.warning(f"'{nome}' já está em execução.")
        return False

    if not Path(path_script).exists():
        logging.error(f"Arquivo não encontrado: {path_script}")
        return False

    try:
        subprocess.Popen(
            [sys.executable, path_script],
            creationflags=subprocess.CREATE_NEW_CONSOLE   # abre em janela separada no Windows
        )
        logging.info(f"'{nome}' iniciado com sucesso.")
        return True
    except Exception as e:
        logging.error(f"Erro ao iniciar '{nome}': {e}")
        return False


def matar_processo(nome_arquivo: str) -> bool:
    """
    Encerra um processo gerenciado pelo nome do arquivo .py.

    Args:
        nome_arquivo: nome do script (ex: 'contagem.py')

    Returns:
        True se o processo foi encerrado, False se não estava rodando.
    """
    gerenciados = verificar_processos_gerenciados()
    alvos = [p for p in gerenciados if p['nome_arquivo'] == nome_arquivo]

    if not alvos:
        logging.warning(f"Processo '{nome_arquivo}' não está ativo ou não é gerenciado.")
        return False

    for proc in alvos:
        try:
            processo = psutil.Process(proc['pid'])
            processo.terminate()
            processo.wait(timeout=5)
            logging.info(f"'{nome_arquivo}' (PID {proc['pid']}) encerrado com sucesso.")
        except psutil.TimeoutExpired:
            processo.kill()
            logging.warning(f"'{nome_arquivo}' forçadamente encerrado (SIGKILL).")
        except psutil.NoSuchProcess:
            logging.warning(f"'{nome_arquivo}' já havia encerrado.")

    return True
