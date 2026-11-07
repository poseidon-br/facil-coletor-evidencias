"""Execução portátil: dados próprios dentro da pasta da ferramenta e liberação das bibliotecas .NET.

O registro de erros (erros.log) e as preferências ficam na pasta "dados", ao
lado da pasta "coletor", e acompanham a ferramenta quando ela é copiada para
outro computador ou para um pen drive. Se essa pasta não aceitar gravação
(mídia somente leitura, por exemplo), os dados vão para
%LOCALAPPDATA%\\ColetorEvidencias, como nas versões anteriores.

Liberação das bibliotecas: ao extrair um zip baixado da internet, o Windows
anexa a cada arquivo a marca de origem (fluxo Zone.Identifier, informação extra
que diz que o arquivo veio da internet). Com essa marca, o .NET Framework se
recusa a carregar as bibliotecas que desenham a janela (pythonnet e
pywebview), e a ferramenta fecha sem abrir. Antes de abrir a janela, a
ferramenta retira a marca só dessas bibliotecas do próprio pacote.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PASTA_PORTATIL = RAIZ / "dados"
PASTA_LOCAL = Path(os.environ.get("LOCALAPPDATA", ".")) / "ColetorEvidencias"
# Pacotes cujas bibliotecas .NET (DLLs gerenciadas) são carregadas pelo .NET Framework ao abrir a janela.
PACOTES_DOTNET = ("pythonnet", "clr_loader", "webview")

_pasta: Path | None = None


def _aceita_gravacao(pasta: Path) -> bool:
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        teste = pasta / f".teste-{uuid.uuid4().hex}"
        teste.write_bytes(b"")
        teste.unlink()
        return True
    except OSError:
        return False


def pasta_dados() -> Path:
    """Pasta do erros.log e das preferências: a da ferramenta, se aceitar gravação; senão, a do usuário."""
    global _pasta
    if _pasta is None:
        _pasta = PASTA_PORTATIL if _aceita_gravacao(PASTA_PORTATIL) else PASTA_LOCAL
        if _pasta == PASTA_PORTATIL:
            _trazer_preferencias_antigas()
    return _pasta


def portatil() -> bool:
    return pasta_dados() == PASTA_PORTATIL


def _trazer_preferencias_antigas() -> None:
    """Na primeira abertura portátil, aproveita as preferências que as versões anteriores gravavam no perfil."""
    novo, antigo = PASTA_PORTATIL / "preferencias.json", PASTA_LOCAL / "preferencias.json"
    try:
        if not novo.exists() and antigo.is_file():
            novo.write_bytes(antigo.read_bytes())
    except OSError:
        pass


def liberar_bibliotecas_dotnet() -> list[str]:
    """Retira a marca de origem da internet das DLLs dos pacotes .NET. Devolve os arquivos liberados."""
    liberados = []
    for pacote in PACOTES_DOTNET:
        try:
            especificacao = importlib.util.find_spec(pacote)
        except (ImportError, ValueError):
            continue
        for local in (especificacao.submodule_search_locations or []) if especificacao else []:
            for dll in Path(local).rglob("*.dll"):
                try:
                    os.remove(f"{dll}:Zone.Identifier")
                    liberados.append(str(dll))
                except OSError:  # sem a marca (o caso comum) ou sem permissão de alteração
                    pass
    return liberados
