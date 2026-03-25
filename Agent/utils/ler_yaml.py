import yaml
from pathlib import Path

# Caminho absoluto para src/scripts.yaml, relativo a este arquivo
_DEFAULT_YAML = Path(__file__).parent.parent / "src" / "scripts.yaml"


def carregar_scripts(caminho_yaml: Path | str = _DEFAULT_YAML) -> list[dict]:
    """Lê o arquivo YAML e retorna a lista de scripts configurados."""
    with open(caminho_yaml, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config["scripts"]


if __name__ == "__main__":
    scripts = carregar_scripts()

    # Acessar individualmente
    for s in scripts:
        print(s["nome"])  # "contagem", "contagem_2", ...
        print(s["path"])  # caminho completo

    # Acessar o primeiro
    primeiro = scripts[0]
    print(primeiro["nome"])  # "contagem"

    # Acessar por índice
    print(scripts[1]["path"])  # caminho do contagem_2
