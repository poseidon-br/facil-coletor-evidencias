"""Captura do som pela captura de retorno do Windows (WASAPI loopback).

Grava o que está saindo para a saída de som padrão, seja caixa, fone com fio,
USB ou Bluetooth, sem configurar mixagem estéreo e sem trocar a saída. Se o
usuário trocar de saída durante a gravação, a captura passa para a nova saída
e a troca é informada.

A captura roda num processo separado. A biblioteca de som (PortAudio), ao ser
encerrada, desfaz uma inicialização do Windows de que a captura de imagem
depende; no mesmo processo, a gravação seguinte falharia. O processo separado
também impede que uma falha no driver de som derrube a coleta.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pyaudiowpatch as pa

TAXA = 48000
CANAIS = 2
FREQUENCIA_TESTE = 1000
LIMIAR_TESTE_DB = -45.0


def _saida_padrao(audio: pa.PyAudio) -> dict:
    wasapi = audio.get_host_api_info_by_type(pa.paWASAPI)
    return audio.get_device_info_by_index(wasapi["defaultOutputDevice"])


def _loopback_de(audio: pa.PyAudio, saida: dict) -> dict:
    for dispositivo in audio.get_loopback_device_info_generator():
        if saida["name"] in dispositivo["name"]:
            return dispositivo
    return audio.get_default_wasapi_loopback()


def nome_saida_padrao() -> str:
    audio = pa.PyAudio()
    try:
        return _saida_padrao(audio)["name"]
    finally:
        audio.terminate()


def _converter(dados: bytes, canais: int, taxa: int) -> bytes:
    """Converte para 48 kHz estéreo, o formato fixo das gravações."""
    if canais == CANAIS and taxa == TAXA:
        return dados
    amostras = np.frombuffer(dados, dtype=np.int16).reshape(-1, canais)
    if canais == 1:
        amostras = np.repeat(amostras, 2, axis=1)
    elif canais > 2:
        amostras = amostras[:, :2]
    if taxa != TAXA and len(amostras):
        posicoes = np.linspace(0, len(amostras) - 1, int(len(amostras) * TAXA / taxa))
        amostras = np.stack([np.interp(posicoes, np.arange(len(amostras)), amostras[:, c])
                             for c in range(2)], axis=1).astype(np.int16)
    return amostras.astype(np.int16).tobytes()


class _CapturaLocal:
    """Entrega blocos PCM 16 bits, 48 kHz, estéreo, ao destino informado."""

    def __init__(self, destino, ao_trocar_saida=None):
        self.destino = destino
        self.ao_trocar_saida = ao_trocar_saida
        self._audio = pa.PyAudio()
        self._fluxo = None
        self._saida = None
        self._parar = threading.Event()
        self._vigia = None

    @property
    def nome_saida(self) -> str | None:
        return self._saida["name"] if self._saida else None

    def _abrir(self) -> None:
        self._saida = _saida_padrao(self._audio)
        loopback = _loopback_de(self._audio, self._saida)
        canais = int(loopback["maxInputChannels"])
        taxa = int(loopback["defaultSampleRate"])

        def ao_receber(dados, quadros, info, estado):
            self.destino(_converter(dados, canais, taxa))
            return (None, pa.paContinue)

        self._fluxo = self._audio.open(format=pa.paInt16, channels=canais, rate=taxa, input=True,
                                       input_device_index=loopback["index"], frames_per_buffer=1024,
                                       stream_callback=ao_receber)
        self._fluxo.start_stream()

    def _fechar_fluxo(self) -> None:
        if self._fluxo:
            try:
                self._fluxo.stop_stream()
                self._fluxo.close()
            except Exception:
                pass
            self._fluxo = None

    def iniciar(self) -> None:
        self._abrir()
        self._vigia = threading.Thread(target=self._vigiar, daemon=True)
        self._vigia.start()

    def _vigiar(self) -> None:
        while not self._parar.wait(2.0):
            try:
                atual = _saida_padrao(self._audio)["name"]
            except Exception:
                continue
            if atual != self.nome_saida:
                anterior = self.nome_saida
                self._fechar_fluxo()
                # A lista de dispositivos só é atualizada recriando o PyAudio.
                self._audio.terminate()
                self._audio = pa.PyAudio()
                self._abrir()
                if self.ao_trocar_saida:
                    self.ao_trocar_saida(anterior, self.nome_saida)

    def parar(self) -> None:
        self._parar.set()
        if self._vigia:
            self._vigia.join(timeout=5)
        self._fechar_fluxo()
        self._audio.terminate()


def _testar_local() -> dict:
    """Toca um tom curto na saída padrão e confere se a captura de retorno o recebe."""
    recebido = []
    captura = _CapturaLocal(recebido.append)
    captura.iniciar()
    audio = pa.PyAudio()
    try:
        saida = _saida_padrao(audio)
        taxa = int(saida["defaultSampleRate"])
        canais = max(1, int(saida["maxOutputChannels"]))
        t = np.arange(int(taxa * 0.6)) / taxa
        tom = (0.25 * np.sin(2 * np.pi * FREQUENCIA_TESTE * t)).astype(np.float32)
        tom = np.repeat(tom[:, None], canais, axis=1).ravel()
        fluxo = audio.open(format=pa.paFloat32, channels=canais, rate=taxa, output=True,
                           output_device_index=saida["index"])
        time.sleep(0.2)
        fluxo.write(tom.tobytes())
        time.sleep(0.4)
        fluxo.close()
    finally:
        nome = captura.nome_saida
        captura.parar()
        audio.terminate()

    amostras = np.frombuffer(b"".join(recebido), dtype=np.int16).astype(np.float64)
    if not len(amostras):
        return {"saida": nome, "captado": False, "nivel_db": None}
    # Energia na frequência do tom, para não confundir com outro som tocando ao mesmo tempo.
    mono = amostras.reshape(-1, 2).mean(axis=1) / 32768.0
    espectro = np.abs(np.fft.rfft(mono)) / len(mono)
    freqs = np.fft.rfftfreq(len(mono), 1 / TAXA)
    faixa = (freqs > FREQUENCIA_TESTE - 30) & (freqs < FREQUENCIA_TESTE + 30)
    nivel = 20 * np.log10(max(espectro[faixa].max() * 2, 1e-9))
    return {"saida": nome, "captado": bool(nivel > LIMIAR_TESTE_DB), "nivel_db": round(float(nivel), 1)}


# ====================================================================== processo separado

RAIZ = Path(__file__).resolve().parents[2]
SEM_JANELA = 0x08000000
BLOCO_LEITURA = 4096 * 4


def _comando(modo: str) -> list[str]:
    return [sys.executable, "-m", "coletor.modulos.som", modo]


class CapturaSom:
    """Mesma interface da captura local, executada em processo separado."""

    def __init__(self, destino, ao_trocar_saida=None):
        self.destino = destino
        self.ao_trocar_saida = ao_trocar_saida
        self.nome_saida: str | None = None
        self._pronto = threading.Event()
        self._erro: str | None = None
        self._processo = None

    def iniciar(self, tempo_limite: float = 15) -> None:
        self._processo = subprocess.Popen(_comando("captura"), cwd=RAIZ, stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          creationflags=SEM_JANELA)
        threading.Thread(target=self._ler_som, daemon=True).start()
        threading.Thread(target=self._ler_avisos, daemon=True).start()
        if not self._pronto.wait(tempo_limite) or self._erro:
            self.parar()
            raise RuntimeError(self._erro or "a captura de som não respondeu")

    def _ler_som(self) -> None:
        saida = self._processo.stdout
        while bloco := saida.read1(BLOCO_LEITURA) if hasattr(saida, "read1") else saida.read(BLOCO_LEITURA):
            self.destino(bloco)

    def _ler_avisos(self) -> None:
        for linha in self._processo.stderr:
            try:
                aviso = json.loads(linha)
            except ValueError:
                continue
            if aviso.get("evento") == "saida":
                self.nome_saida = aviso["nome"]
                self._pronto.set()
            elif aviso.get("evento") == "troca":
                self.nome_saida = aviso["nova"]
                if self.ao_trocar_saida:
                    self.ao_trocar_saida(aviso["anterior"], aviso["nova"])
            elif aviso.get("evento") == "erro":
                self._erro = aviso["mensagem"]
                self._pronto.set()

    def parar(self) -> None:
        if not self._processo:
            return
        try:
            self._processo.stdin.close()  # sinal de parada para o processo de captura
            self._processo.wait(timeout=10)
        except Exception:
            self._processo.kill()


def testar() -> dict:
    """Teste de som em processo separado."""
    resultado = subprocess.run(_comando("teste"), cwd=RAIZ, capture_output=True, timeout=60,
                               creationflags=SEM_JANELA)
    try:
        return json.loads(resultado.stdout.decode().strip().splitlines()[-1])
    except Exception:
        return {"saida": None, "captado": False, "nivel_db": None,
                "erro": resultado.stderr.decode(errors="replace")[-300:]}


def _avisar(**dados) -> None:
    sys.stderr.write(json.dumps(dados, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def _processo_captura() -> None:
    saida = sys.stdout.buffer
    trava = threading.Lock()

    def escrever(dados: bytes) -> None:
        with trava:
            saida.write(dados)
            saida.flush()

    captura = _CapturaLocal(escrever, lambda anterior, nova: _avisar(evento="troca", anterior=anterior, nova=nova))
    try:
        captura.iniciar()
    except Exception as erro:
        _avisar(evento="erro", mensagem=str(erro))
        return
    _avisar(evento="saida", nome=captura.nome_saida)
    sys.stdin.read()  # bloqueia até o processo principal fechar a entrada
    captura.parar()


if __name__ == "__main__":
    if sys.argv[1:] == ["captura"]:
        _processo_captura()
    elif sys.argv[1:] == ["teste"]:
        print(json.dumps(_testar_local(), ensure_ascii=False))
