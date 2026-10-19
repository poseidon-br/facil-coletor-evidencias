"""Registro do ambiente: o computador em que a coleta foi feita.

Não impede fraudes, mas documenta condições que interessam a quem avalia a
prova: máquina virtual, acesso remoto ativo, privilégio de administrador e os
programas em execução.
"""

from __future__ import annotations

import ctypes
import getpass
import json
import platform
import socket
import subprocess
import sys
import time
import winreg
from datetime import datetime

import psutil

from .tempo import fuso

SM_REMOTESESSION = 0x1000

# Programas de acesso remoto mais comuns. Se algum estiver em execução, o
# relatório registra que o computador podia estar sendo operado à distância.
PROGRAMAS_ACESSO_REMOTO = {
    "anydesk.exe": "AnyDesk",
    "teamviewer.exe": "TeamViewer",
    "teamviewer_service.exe": "TeamViewer",
    "rustdesk.exe": "RustDesk",
    "remoting_host.exe": "Chrome Remote Desktop",
    "vncserver.exe": "VNC",
    "winvnc.exe": "VNC",
    "tvnserver.exe": "TightVNC",
    "rutserv.exe": "Remote Utilities",
    "screenconnect.clientservice.exe": "ScreenConnect",
    "splashtopstreamer.exe": "Splashtop",
    "parsecd.exe": "Parsec",
    "quickassist.exe": "Assistência Rápida do Windows",
    "msra.exe": "Assistência Remota do Windows",
}

INDICIOS_MAQUINA_VIRTUAL = ("vmware", "virtualbox", "innotek", "qemu", "kvm", "xen",
                            "parallels", "bochs", "virtual machine", "hvm domu")

SEM_JANELA = 0x08000000  # CREATE_NO_WINDOW


def _versao_windows() -> dict:
    dados = {"plataforma": platform.platform(), "compilacao": sys.getwindowsversion().build}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as chave:
            for nome in ("ProductName", "DisplayVersion", "EditionID", "UBR"):
                try:
                    dados[nome] = winreg.QueryValueEx(chave, nome)[0]
                except OSError:
                    pass
    except OSError:
        pass
    # O registro ainda diz "Windows 10" em instalações do Windows 11.
    if dados["compilacao"] >= 22000 and str(dados.get("ProductName", "")).startswith("Windows 10"):
        dados["ProductName"] = dados["ProductName"].replace("Windows 10", "Windows 11", 1)
    return dados


def _fabricante_modelo() -> dict:
    comando = ("Get-CimInstance Win32_ComputerSystem | "
               "Select-Object Manufacturer,Model | ConvertTo-Json -Compress")
    try:
        saida = subprocess.run(["powershell", "-NoProfile", "-Command", comando],
                               capture_output=True, text=True, timeout=20,
                               creationflags=SEM_JANELA).stdout
        dados = json.loads(saida)
        return {"fabricante": dados.get("Manufacturer"), "modelo": dados.get("Model")}
    except Exception:
        return {"fabricante": None, "modelo": None}


def _eh_administrador() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _processos() -> list[dict]:
    lista = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        info = proc.info
        lista.append({"pid": info["pid"], "nome": info["name"], "caminho": info["exe"]})
    return sorted(lista, key=lambda p: ((p["nome"] or "").lower(), p["pid"]))


def registrar() -> dict:
    """Coleta o retrato do ambiente. O resultado é gravado em ambiente.json."""
    versao = _versao_windows()
    maquina = _fabricante_modelo()
    processos = _processos()

    texto_maquina = f"{maquina['fabricante']} {maquina['modelo']}".lower()
    indicio_vm = next((i for i in INDICIOS_MAQUINA_VIRTUAL if i in texto_maquina), None)

    sessao_remota = bool(ctypes.windll.user32.GetSystemMetrics(SM_REMOTESESSION))
    remotos = sorted({PROGRAMAS_ACESSO_REMOTO[p["nome"].lower()] for p in processos
                      if p["nome"] and p["nome"].lower() in PROGRAMAS_ACESSO_REMOTO})

    return {
        "windows": versao,
        "computador": {"nome": socket.gethostname(), "usuario": getpass.getuser(), **maquina},
        "maquina_virtual": {"detectada": indicio_vm is not None, "indicio": indicio_vm},
        "acesso_remoto": {
            "sessao_remota": sessao_remota,
            "programas_em_execucao": remotos,
            "detectado": sessao_remota or bool(remotos),
        },
        "administrador": _eh_administrador(),
        "fuso_horario": {"nome": time.tzname[0], "deslocamento": fuso(datetime.now().astimezone())},
        "processos": processos,
    }


def resumo(ambiente: dict) -> dict:
    """Campos do ambiente que vão para o log e para o relatório."""
    w = ambiente["windows"]
    return {
        "windows": f"{w.get('ProductName', 'Windows')} {w.get('DisplayVersion', '')}".strip()
                   + f" (compilação {w['compilacao']}.{w.get('UBR', 0)})",
        "computador": ambiente["computador"]["nome"],
        "fabricante_modelo": " ".join(filter(None, [ambiente["computador"]["fabricante"],
                                                    ambiente["computador"]["modelo"]])),
        "maquina_virtual": ambiente["maquina_virtual"]["detectada"],
        "acesso_remoto": ambiente["acesso_remoto"]["detectado"],
        "programas_acesso_remoto": ambiente["acesso_remoto"]["programas_em_execucao"],
        "administrador": ambiente["administrador"],
        "quantidade_processos": len(ambiente["processos"]),
    }
