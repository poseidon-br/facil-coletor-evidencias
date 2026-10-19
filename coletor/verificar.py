"""Verificação independente de uma pasta de coleta.

Uso: python -m coletor.verificar "caminho da pasta COLETA_..."
Confere o log encadeado, o manifesto e a correspondência dos carimbos do tempo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .nucleo.carimbo import ler_resposta
from .nucleo.hashing import sha256_arquivo
from .nucleo.log import ler_eventos, verificar_cadeia
from .nucleo import manifesto


def verificar(pasta: Path) -> list[str]:
    pasta = Path(pasta)
    verif = pasta / "Verificacao"
    problemas = []

    eventos = ler_eventos(verif / "log.jsonl")
    fechamento = ler_eventos(verif / "log_fechamento.jsonl") if (verif / "log_fechamento.jsonl").is_file() else []
    problemas += [f"log: {p}" for p in verificar_cadeia(eventos + fechamento)]

    dados_manifesto = json.loads((verif / "manifesto.json").read_text(encoding="utf-8"))
    if dados_manifesto["hash_final_log"] != eventos[-1]["hash"]:
        problemas.append("log: o último evento não corresponde ao registrado no manifesto")
    problemas += [f"manifesto: {p}" for p in manifesto.verificar(pasta)]

    hash_manifesto = bytes.fromhex(sha256_arquivo(verif / "manifesto.json"))
    hash_evento0 = bytes.fromhex(eventos[0]["hash"])
    for tsr in sorted((verif / "carimbos").glob("*.tsr")):
        esperado = hash_manifesto if tsr.name.startswith("fechamento") else hash_evento0
        try:
            info = ler_resposta(tsr.read_bytes())
            if info["resumo"] != esperado:
                problemas.append(f"carimbo {tsr.name}: não corresponde ao hash esperado")
        except Exception as erro:
            problemas.append(f"carimbo {tsr.name}: ilegível ({erro})")
    return problemas


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    problemas = verificar(Path(sys.argv[1]))
    if problemas:
        print("PROBLEMAS ENCONTRADOS:")
        for p in problemas:
            print(" -", p)
        return 1
    print("Coleta íntegra: log encadeado, manifesto e carimbos conferem.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
