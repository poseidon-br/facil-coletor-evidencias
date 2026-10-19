"""Log encadeado.

Cada evento é uma linha JSON. O hash de cada evento é o SHA-256 da sua forma
canônica (RFC 8785) sem o próprio campo "hash", e cada evento guarda o hash do
anterior. Alterar, inserir ou remover qualquer linha quebra a cadeia.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import rfc8785

from .hashing import sha256_bytes
from .tempo import agora

HASH_INICIAL = "0" * 64


def forma_canonica(evento: dict) -> bytes:
    sem_hash = {k: v for k, v in evento.items() if k != "hash"}
    return rfc8785.dumps(sem_hash)


def calcular_hash(evento: dict) -> str:
    return sha256_bytes(forma_canonica(evento))


class LogEncadeado:
    """Escreve eventos encadeados num arquivo JSONL, gravando cada um no disco."""

    def __init__(self, caminho: Path, seq_inicial: int = 0, hash_anterior: str = HASH_INICIAL):
        self.caminho = Path(caminho)
        self._seq = seq_inicial
        self._hash_anterior = hash_anterior
        self._trava = threading.Lock()
        self._arquivo = open(self.caminho, "a", encoding="utf-8", newline="\n")

    @property
    def ultimo_hash(self) -> str:
        return self._hash_anterior

    @property
    def proximo_seq(self) -> int:
        return self._seq

    def registrar(self, modulo: str, tipo: str, dados: dict | None = None) -> dict:
        with self._trava:
            evento = {"seq": self._seq, **agora(), "modulo": modulo, "tipo": tipo,
                      "dados": dados or {}, "hash_anterior": self._hash_anterior}
            evento["hash"] = calcular_hash(evento)
            self._arquivo.write(json.dumps(evento, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._arquivo.flush()
            os.fsync(self._arquivo.fileno())
            self._seq += 1
            self._hash_anterior = evento["hash"]
            return evento

    def fechar(self) -> None:
        with self._trava:
            if not self._arquivo.closed:
                self._arquivo.close()


def ler_eventos(caminho: Path) -> list[dict]:
    with open(caminho, encoding="utf-8") as f:
        return [json.loads(linha) for linha in f if linha.strip()]


def verificar_cadeia(eventos: list[dict], hash_anterior: str = HASH_INICIAL,
                     seq_inicial: int = 0) -> list[str]:
    """Retorna a lista de problemas encontrados; vazia quando a cadeia está íntegra."""
    problemas = []
    for esperado_seq, evento in enumerate(eventos, start=seq_inicial):
        if evento.get("seq") != esperado_seq:
            problemas.append(f"evento {evento.get('seq')}: sequência esperada {esperado_seq}")
        if evento.get("hash_anterior") != hash_anterior:
            problemas.append(f"evento {evento.get('seq')}: não aponta para o evento anterior")
        if calcular_hash(evento) != evento.get("hash"):
            problemas.append(f"evento {evento.get('seq')}: conteúdo alterado (hash não confere)")
        hash_anterior = evento.get("hash")
    return problemas
