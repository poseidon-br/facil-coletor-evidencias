"""SHA-256, o único algoritmo de hash usado pela ferramenta."""

from __future__ import annotations

import hashlib
from pathlib import Path

BLOCO = 1024 * 1024


def sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def sha256_arquivo(caminho: str | Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while bloco := f.read(BLOCO):
            h.update(bloco)
    return h.hexdigest()
