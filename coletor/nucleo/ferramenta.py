"""Identificação da própria ferramenta: versão, commit e hashes.

Na versão de desenvolvimento não há build assinado para conferir, e o
relatório diz isso. No build oficial, os hashes calculados aqui serão
comparados com o manifesto assinado do build.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .. import VERSAO
from .hashing import sha256_arquivo, sha256_bytes

RAIZ_PACOTE = Path(__file__).resolve().parents[1]
SEM_JANELA = 0x08000000
# Gravado pelo empacotamento ao lado da pasta do código, onde não há repositório Git.
ARQUIVO_BUILD = RAIZ_PACOTE.parent / "build.json"


def _valido(commit) -> bool:
    return isinstance(commit, str) and len(commit) == 40 and all(c in "0123456789abcdef" for c in commit)


def _commit() -> str | None:
    try:
        saida = subprocess.run(["git", "rev-parse", "HEAD"], cwd=RAIZ_PACOTE.parent,
                               capture_output=True, text=True, timeout=10,
                               creationflags=SEM_JANELA)
        commit = saida.stdout.strip()
        if _valido(commit):
            return commit
    except Exception:
        pass
    try:
        commit = json.loads(ARQUIVO_BUILD.read_text(encoding="utf-8")).get("commit")
        return commit if _valido(commit) else None
    except Exception:
        return None


def hashes_do_codigo() -> dict[str, str]:
    """SHA-256 de cada arquivo do código da ferramenta, em ordem de caminho."""
    arquivos = sorted(p for p in RAIZ_PACOTE.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts)
    return {p.relative_to(RAIZ_PACOTE).as_posix(): sha256_arquivo(p) for p in arquivos}


def identificar(componentes: dict[str, str | None] | None = None) -> dict:
    """Retorna versão, commit, hash do conjunto do código e dos componentes externos."""
    codigo = hashes_do_codigo()
    conjunto = sha256_bytes("\n".join(f"{h}  {c}" for c, h in codigo.items()).encode())
    dados = {
        "versao": VERSAO,
        "commit": _commit(),
        "oficial": False,
        "motivo_nao_oficial": "versão de desenvolvimento, sem build assinado para conferência",
        "hash_codigo": conjunto,
        "arquivos_codigo": codigo,
        "python": {"versao": sys.version.split()[0], "executavel": sys.executable,
                   "sha256": sha256_arquivo(sys.executable)},
        "componentes": {},
    }
    for nome, caminho in (componentes or {}).items():
        if caminho and Path(caminho).is_file():
            dados["componentes"][nome] = {"caminho": str(caminho), "sha256": sha256_arquivo(caminho)}
        else:
            dados["componentes"][nome] = {"caminho": caminho, "sha256": None}
    return dados
