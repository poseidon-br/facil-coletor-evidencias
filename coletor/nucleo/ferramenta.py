"""Identificação da própria ferramenta: versão, commit e hashes.

O build oficial é montado nos servidores do GitHub a partir de um commit
público, e o arquivo build.json do pacote guarda a versão, o commit e o hash
do conjunto do código. A cada coleta, o hash é recalculado e comparado com o
gravado: se conferir, o relatório informa o build oficial; se não, ou se a
ferramenta rodar a partir do código-fonte, o relatório diz isso. A conferência
é feita pela própria ferramenta; a conferência por terceiros usa a versão, o
commit e o hash publicados na página de versões do repositório.
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


def _build() -> dict:
    try:
        dados = json.loads(ARQUIVO_BUILD.read_text(encoding="utf-8-sig"))
        return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


def _commit() -> str | None:
    commit = _build().get("commit")
    if _valido(commit):
        return commit
    try:
        saida = subprocess.run(["git", "rev-parse", "HEAD"], cwd=RAIZ_PACOTE.parent,
                               capture_output=True, text=True, timeout=10,
                               creationflags=SEM_JANELA)
        commit = saida.stdout.strip()
        if _valido(commit):
            return commit
    except Exception:
        pass
    return None


def hashes_do_codigo() -> dict[str, str]:
    """SHA-256 de cada arquivo do código da ferramenta, em ordem de caminho."""
    arquivos = sorted(p for p in RAIZ_PACOTE.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts)
    return {p.relative_to(RAIZ_PACOTE).as_posix(): sha256_arquivo(p) for p in arquivos}


def hash_do_codigo(codigo: dict[str, str] | None = None) -> str:
    """SHA-256 do conjunto: a lista "hash  caminho" de todos os arquivos do código."""
    codigo = hashes_do_codigo() if codigo is None else codigo
    return sha256_bytes("\n".join(f"{h}  {c}" for c, h in codigo.items()).encode())


def conferir_build(conjunto: str | None = None) -> tuple[bool, str | None]:
    """Diz se o código em execução é o do build oficial e, se não for, o motivo."""
    build = _build()
    if build.get("tipo") != "oficial":
        return False, "execução fora do build oficial (código-fonte ou pacote de teste)"
    if build.get("versao") != VERSAO or build.get("hash_codigo") != (conjunto or hash_do_codigo()):
        return False, "o código em execução não confere com a lista de hashes do build oficial"
    return True, None


def identificar(componentes: dict[str, str | None] | None = None) -> dict:
    """Retorna versão, commit, hash do conjunto do código e dos componentes externos."""
    codigo = hashes_do_codigo()
    conjunto = hash_do_codigo(codigo)
    oficial, motivo = conferir_build(conjunto)
    dados = {
        "versao": VERSAO,
        "commit": _commit(),
        "oficial": oficial,
        "motivo_nao_oficial": motivo,
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
