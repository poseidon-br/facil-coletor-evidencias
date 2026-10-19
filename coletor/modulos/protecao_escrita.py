"""Bloqueio de escrita em dispositivos USB pelo registro do Windows.

A chave StorageDevicePolicies, valor WriteProtect=1, faz o Windows recusar
gravações em dispositivos USB conectados depois da ativação. A escrita nessa
chave exige privilégio de administrador, por isso este módulo também roda como
auxiliar elevado (python -m coletor.modulos.protecao_escrita ativar|restaurar).

O processo principal nunca confia no auxiliar: antes de ativar, lê o valor
anterior por conta própria (a leitura não exige privilégio) e, depois de cada
comando, confere o resultado relendo o registro.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import subprocess
import sys
import winreg
from pathlib import Path

CAMINHO_CHAVE = r"SYSTEM\CurrentControlSet\Control\StorageDevicePolicies"
VALOR = "WriteProtect"
SEM_JANELA = 0x08000000
ERRO_CANCELADO = 1223  # usuário recusou a confirmação do Windows (UAC)
ERRO_PROTECAO_ESCRITA = 19  # ERROR_WRITE_PROTECT

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_kernel32.CreateFileW.restype = wt.HANDLE
_IDENTIFICADOR_INVALIDO = wt.HANDLE(-1).value

METODO = ("valor WriteProtect=1 na chave StorageDevicePolicies do registro do Windows, equivalente à "
          "política \"Discos removíveis: negar acesso de gravação\"")


def ler_valor() -> int | None:
    """Valor atual de WriteProtect, ou None se a chave ou o valor não existirem."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CAMINHO_CHAVE) as chave:
            valor, _ = winreg.QueryValueEx(chave, VALOR)
            return int(valor)
    except OSError:
        return None


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wt.HWND),
        ("lpVerb", wt.LPCWSTR), ("lpFile", wt.LPCWSTR), ("lpParameters", wt.LPCWSTR),
        ("lpDirectory", wt.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wt.HINSTANCE),
        ("lpIDList", ctypes.c_void_p), ("lpClass", wt.LPCWSTR), ("hkeyClass", wt.HKEY),
        ("dwHotKey", wt.DWORD), ("hIconOrMonitor", wt.HANDLE), ("hProcess", wt.HANDLE),
    ]


def _executar_elevado(*argumentos: str, espera_s: int = 120) -> dict:
    """Roda este módulo como administrador (confirmação do Windows) e espera terminar."""
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40  # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = sys.executable
    info.lpParameters = " ".join(["-m", "coletor.modulos.protecao_escrita", *argumentos])
    info.lpDirectory = str(Path(__file__).resolve().parents[2])
    info.nShow = 0  # SW_HIDE
    if not _shell32.ShellExecuteExW(ctypes.byref(info)):
        erro = ctypes.get_last_error()
        if erro == ERRO_CANCELADO:
            return {"codigo": None, "erro": "confirmação de administrador recusada pelo operador"}
        return {"codigo": None, "erro": f"não foi possível iniciar o auxiliar (erro {erro} do Windows)"}
    try:
        _kernel32.WaitForSingleObject(info.hProcess, espera_s * 1000)
        codigo = wt.DWORD()
        _kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(codigo))
        return {"codigo": codigo.value, "erro": None}
    finally:
        _kernel32.CloseHandle(info.hProcess)


def ativar() -> dict:
    """Ativa o bloqueio pelo auxiliar elevado e confere o resultado relendo o registro."""
    valor_anterior = ler_valor()
    execucao = _executar_elevado("ativar")
    valor_atual = ler_valor()
    return {"valor_anterior": valor_anterior, "valor_atual": valor_atual,
            "sucesso": valor_atual == 1,
            "erro": execucao["erro"] or (None if valor_atual == 1 else "a gravação no registro não teve efeito")}


def restaurar(valor_anterior: int | None) -> dict:
    """Restaura o valor anterior (ou remove o valor, se não existia) e confere relendo."""
    argumento = "remover" if valor_anterior is None else str(int(valor_anterior))
    execucao = _executar_elevado("restaurar", argumento)
    valor_atual = ler_valor()
    return {"valor_restaurado": valor_anterior, "valor_atual": valor_atual,
            "sucesso": valor_atual == valor_anterior,
            "erro": execucao["erro"] or (None if valor_atual == valor_anterior
                                         else "a gravação no registro não teve efeito")}


def testar_somente_leitura(letra: str) -> bool | None:
    """Tenta abrir para escrita um arquivo existente da unidade, esperando a recusa do Windows.

    Só deve ser chamado com a política ativa, para nunca abrir para escrita um
    dispositivo desprotegido. Devolve True (recusado por proteção de escrita),
    False (abertura aceita) ou None (sem arquivo para testar ou outro erro).
    """
    raiz = Path(f"{letra}:\\")
    alvo = next((p for p in raiz.glob("*") if p.is_file()), None)
    if alvo is None:
        return None
    GENERIC_WRITE, OPEN_EXISTING = 0x40000000, 3
    identificador = _kernel32.CreateFileW(str(alvo), GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
    if identificador in (None, _IDENTIFICADOR_INVALIDO):
        return True if ctypes.get_last_error() == ERRO_PROTECAO_ESCRITA else None
    _kernel32.CloseHandle(identificador)
    return False


def volumes_usb() -> list[dict]:
    """Unidades com letra cujos discos estão no barramento USB."""
    comando = (
        "Get-Partition | Where-Object DriveLetter | ForEach-Object { "
        "$disco = $_ | Get-Disk; if ($disco.BusType -eq 'USB') { "
        "$vol = Get-Volume -DriveLetter $_.DriveLetter; [PSCustomObject]@{ "
        "letra=[string]$_.DriveLetter; rotulo=$vol.FileSystemLabel; sistema=$vol.FileSystem; "
        "dispositivo=$disco.FriendlyName; serie=([string]$disco.SerialNumber).Trim(); "
        "tamanho=$vol.Size } } } | ConvertTo-Json -Compress"
    )
    try:
        saida = subprocess.run(["powershell", "-NoProfile", "-Command", comando],
                               capture_output=True, text=True, timeout=25,
                               creationflags=SEM_JANELA).stdout.strip()
        if not saida:
            return []
        dados = json.loads(saida)
        return dados if isinstance(dados, list) else [dados]
    except Exception:
        return []


def _principal(argumentos: list[str]) -> int:
    """Corpo do auxiliar elevado: só grava o registro e devolve o código de saída."""
    try:
        if argumentos[:1] == ["ativar"]:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, CAMINHO_CHAVE, 0,
                                    winreg.KEY_SET_VALUE) as chave:
                winreg.SetValueEx(chave, VALOR, 0, winreg.REG_DWORD, 1)
            return 0
        if len(argumentos) == 2 and argumentos[0] == "restaurar":
            if argumentos[1] == "remover":
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CAMINHO_CHAVE, 0,
                                        winreg.KEY_SET_VALUE) as chave:
                        winreg.DeleteValue(chave, VALOR)
                except FileNotFoundError:
                    pass
                return 0
            if argumentos[1] in ("0", "1"):
                with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, CAMINHO_CHAVE, 0,
                                        winreg.KEY_SET_VALUE) as chave:
                    winreg.SetValueEx(chave, VALOR, 0, winreg.REG_DWORD, int(argumentos[1]))
                return 0
        return 11
    except OSError:
        return 10


if __name__ == "__main__":
    sys.exit(_principal(sys.argv[1:]))
