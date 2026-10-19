"""Localização dos componentes externos (Chromium e ffmpeg).

No build oficial eles são baixados na primeira execução, com hash fixado no
manifesto do build, para a pasta "componentes". Na versão de desenvolvimento,
a mesma pasta é preenchida manualmente, e as variáveis de ambiente
COLETOR_CHROMIUM e COLETOR_FFMPEG permitem apontar outro local.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PASTA = RAIZ / "componentes"


def chromium() -> str | None:
    caminho = os.environ.get("COLETOR_CHROMIUM") or PASTA / "chrome-win64" / "chrome.exe"
    return str(caminho) if Path(caminho).is_file() else None


def ffmpeg() -> str | None:
    caminho = os.environ.get("COLETOR_FFMPEG") or PASTA / "ffmpeg" / "ffmpeg.exe"
    if Path(caminho).is_file():
        return str(caminho)
    return shutil.which("ffmpeg")


def todos() -> dict[str, str | None]:
    return {"Chromium": chromium(), "ffmpeg": ffmpeg()}
