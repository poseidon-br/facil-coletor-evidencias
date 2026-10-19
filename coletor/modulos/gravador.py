"""Gravador único de imagem e som, para o navegador e para a tela.

Imagem pelo Windows Graphics Capture (janela do navegador ou monitor inteiro),
som pela captura de retorno do Windows. A gravação é dividida em segmentos de
até 10 MB, cada um com hash próprio, para permitir a juntada no PJe e no eproc.
Cada quadro leva a data e a hora do computador gravadas na imagem.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from .. import componentes
from ..nucleo.sessao import LIMITE_JUNTADA, Item, Sessao
from ..nucleo.tempo import agora
from . import som

QUADROS_POR_SEGUNDO = 10
LIMITE_SEGMENTO = int(LIMITE_JUNTADA * 0.88)  # folga para o som e o encerramento do arquivo
BYTES_SOM_POR_SEGUNDO = 96_000 // 8
LARGURA_MAXIMA = 2560
SEM_JANELA = 0x08000000
FONTE = "C\\:/Windows/Fonts/consola.ttf"


def localizar_ffmpeg() -> str:
    caminho = componentes.ffmpeg()
    if not caminho:
        raise RuntimeError("ffmpeg não encontrado")
    return caminho


class _Segmento:
    def __init__(self, pasta: Path, largura: int, altura: int, ffmpeg: str):
        self.largura, self.altura = largura, altura
        self.ffmpeg = ffmpeg
        self.inicio = agora()
        self.t0 = time.monotonic()
        epoch = time.time()
        self.video = pasta / f"_seg_{int(epoch * 1000)}.mp4"
        self.audio = self.video.with_suffix(".wav")
        relogio = (f"drawtext=fontfile='{FONTE}':fontsize=18:fontcolor=white:box=1:boxcolor=black@0.65:"
                   f"boxborderw=4:x=8:y=h-th-12:"
                   f"text='%{{pts\\:localtime\\:{epoch:.3f}\\:%d/%m/%Y %H\\\\\\:%M\\\\\\:%S}}'")
        self.processo = subprocess.Popen(
            [ffmpeg, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra",
             "-s", f"{largura}x{altura}", "-r", str(QUADROS_POR_SEGUNDO), "-i", "-",
             "-vf", relogio, "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
             "-maxrate", "900k", "-bufsize", "1800k", "-pix_fmt", "yuv420p",
             "-g", str(QUADROS_POR_SEGUNDO * 5), "-movflags", "+frag_keyframe+empty_moov",
             str(self.video)],
            stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=SEM_JANELA)
        self.wav = wave.open(str(self.audio), "wb")
        self.wav.setnchannels(som.CANAIS)
        self.wav.setsampwidth(2)
        self.wav.setframerate(som.TAXA)
        self.quadros = 0
        self.amostras = 0
        self._trava = threading.Lock()

    def escrever_quadro(self, dados: bytes) -> None:
        self.processo.stdin.write(dados)
        self.quadros += 1

    def escrever_som(self, dados: bytes) -> None:
        with self._trava:
            self.wav.writeframes(dados)
            self.amostras += len(dados) // 4

    def completar_som(self, ate_amostras: int | None = None) -> None:
        """Preenche com silêncio os intervalos em que a saída de som não entregou dados."""
        with self._trava:
            esperado = ate_amostras if ate_amostras is not None else int((time.monotonic() - self.t0) * som.TAXA)
            falta = esperado - self.amostras
            if falta > (som.TAXA // 10 if ate_amostras is None else 0):
                self.wav.writeframes(b"\x00" * falta * 4)
                self.amostras += falta

    def tamanho_estimado(self) -> int:
        tamanho_video = self.video.stat().st_size if self.video.exists() else 0
        return tamanho_video + int(self.amostras / som.TAXA * BYTES_SOM_POR_SEGUNDO)

    def finalizar(self, destino: Path) -> dict:
        self.fim = agora()
        self.processo.stdin.close()
        self.processo.wait(timeout=120)
        duracao = self.quadros / QUADROS_POR_SEGUNDO
        alvo = int(duracao * som.TAXA)
        self.completar_som(alvo)
        with self._trava:
            self.wav.close()
        subprocess.run(
            [self.ffmpeg, "-loglevel", "error", "-y", "-i", str(self.video), "-i", str(self.audio),
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "96k",
             "-t", f"{duracao:.3f}", "-movflags", "+faststart", str(destino)],
            check=True, capture_output=True, creationflags=SEM_JANELA, timeout=300)
        self.video.unlink(missing_ok=True)
        self.audio.unlink(missing_ok=True)
        return {"inicio": self.inicio["local"], "fim": self.fim["local"], "duracao_s": round(duracao, 1),
                "largura": self.largura, "altura": self.altura}


class Gravador:
    """Grava uma janela (pelo identificador HWND) ou um monitor inteiro."""

    def __init__(self, sessao: Sessao, item: Item, *, hwnd: int | None = None, monitor: int | None = None,
                 descricao_alvo: str, descricao_som: str | None = None):
        self.sessao, self.item = sessao, item
        self.hwnd, self.monitor = hwnd, monitor
        self.descricao_alvo = descricao_alvo
        self.descricao_som = descricao_som
        self.ffmpeg = localizar_ffmpeg()
        self.pasta_temp = sessao.pasta / "Verificacao" / "_gravacao"
        self.pasta_temp.mkdir(parents=True, exist_ok=True)
        self._quadro = None
        self._trava_quadro = threading.Lock()
        self._segmento: _Segmento | None = None
        self._trava_segmento = threading.Lock()
        self._pausado = threading.Event()
        self._parar = threading.Event()
        self._janela_fechada = False
        self.segmentos = 0
        self.tempo_gravado = 0.0
        self.ativo = False

    # ---------------------------------------------------------------- fontes

    def _ao_receber_quadro(self, quadro, controle) -> None:
        if self._parar.is_set():
            controle.stop()
            return
        imagem = quadro.frame_buffer
        if imagem.shape[1] > LARGURA_MAXIMA:
            imagem = imagem[::2, ::2]
        altura, largura = imagem.shape[0] & ~1, imagem.shape[1] & ~1
        with self._trava_quadro:
            self._quadro = np.ascontiguousarray(imagem[:altura, :largura])

    def _ao_fechar(self) -> None:
        self._janela_fechada = True

    def _ao_receber_som(self, dados: bytes) -> None:
        with self._trava_segmento:
            if self._segmento and not self._pausado.is_set():
                self._segmento.escrever_som(dados)

    def _ao_trocar_saida(self, anterior: str, nova: str) -> None:
        self.sessao.log.registrar(self.item.tipo, "som_saida_trocada",
                                  {"item": self.item.numero, "anterior": anterior, "nova": nova})

    # ---------------------------------------------------------------- controle

    def iniciar(self) -> None:
        from windows_capture import WindowsCapture

        captura = WindowsCapture(cursor_capture=True, draw_border=None, minimum_update_interval=50,
                                 window_hwnd=self.hwnd, monitor_index=self.monitor)
        captura.event(self._fn_quadro())
        captura.event(self._fn_fechado())
        self._controle = captura.start_free_threaded()

        self._som = som.CapturaSom(self._ao_receber_som, self._ao_trocar_saida)
        self._som.iniciar()
        saida = self._som.nome_saida
        descricao = self.descricao_som or f"saída inteira do Windows ({saida})"
        self.sessao.log.registrar(self.item.tipo, "som_origem", {
            "item": self.item.numero, "modo": "saida_inteira", "saida": saida, "descricao": descricao,
            "motivo": "captura só do navegador ainda não implementada nesta versão de teste"
            if self.item.tipo in ("site", "whatsapp") else None})

        espera = time.monotonic() + 10
        while self._quadro is None and time.monotonic() < espera and not self._janela_fechada:
            time.sleep(0.05)
        if self._quadro is None:
            self.parar_fontes()
            raise RuntimeError("a captura de imagem não entregou nenhum quadro")
        altura, largura = self._quadro.shape[:2]
        self.sessao.log.registrar(self.item.tipo, "gravacao_iniciada", {
            "item": self.item.numero, "alvo": self.descricao_alvo, "largura": largura, "altura": altura,
            "quadros_por_segundo": QUADROS_POR_SEGUNDO, "limite_segmento_bytes": LIMITE_JUNTADA})
        self.ativo = True
        self._laco = threading.Thread(target=self._gravar, daemon=True)
        self._laco.start()

    def _fn_quadro(self):
        def on_frame_arrived(quadro, controle):
            self._ao_receber_quadro(quadro, controle)
        return on_frame_arrived

    def _fn_fechado(self):
        def on_closed():
            self._ao_fechar()
        return on_closed

    def _gravar(self) -> None:
        while not self._parar.is_set():
            if self._pausado.is_set() or self._janela_fechada:
                time.sleep(0.05)
                continue
            with self._trava_quadro:
                quadro = self._quadro
            atual = self._segmento
            if atual is None or (atual.altura, atual.largura) != quadro.shape[:2]:
                self._trocar_segmento(quadro.shape[1], quadro.shape[0])
                atual = self._segmento
            # Quadros devidos pelo relógio: se o laço atrasou, o último quadro é repetido,
            # o que mantém a duração do vídeo igual ao tempo real e o som sincronizado.
            devidos = int((time.monotonic() - atual.t0) * QUADROS_POR_SEGUNDO) + 1 - atual.quadros
            dados = quadro.tobytes()
            try:
                for _ in range(max(0, min(devidos, QUADROS_POR_SEGUNDO * 2))):
                    atual.escrever_quadro(dados)
            except (BrokenPipeError, OSError):
                erro = atual.processo.stderr.read().decode(errors="replace")[-300:]
                self.sessao.ocorrencia(f"Falha no codificador de vídeo: {erro}", "alerta",
                                       self.item.numero, self.item.tipo)
                self._parar.set()
                break
            atual.completar_som()
            if atual.tamanho_estimado() > LIMITE_SEGMENTO:
                self._trocar_segmento(quadro.shape[1], quadro.shape[0])
            time.sleep(max(0.0, (atual.quadros / QUADROS_POR_SEGUNDO) - (time.monotonic() - atual.t0)))
        if self._janela_fechada and not self._parar.is_set():
            self.sessao.ocorrencia("A janela gravada foi fechada.", "informacao", self.item.numero, self.item.tipo)

    def _trocar_segmento(self, largura: int, altura: int) -> None:
        self._fechar_segmento()
        with self._trava_segmento:
            self._segmento = _Segmento(self.pasta_temp, largura, altura, self.ffmpeg)

    def _fechar_segmento(self) -> None:
        with self._trava_segmento:
            segmento, self._segmento = self._segmento, None
        if segmento is None or segmento.quadros == 0:
            return
        destino = self.item.proximo_arquivo("video", "mp4")
        dados = segmento.finalizar(destino)
        self.segmentos += 1
        self.tempo_gravado += dados["duracao_s"]
        self.sessao.registrar_evidencia(self.item, destino, "video", {**dados, "segmento": self.segmentos})
        if destino.stat().st_size > LIMITE_JUNTADA:
            self.sessao.ocorrencia(f"O segmento {destino.name} passou de 10 MB.", "alerta",
                                   self.item.numero, self.item.tipo)

    def pausar(self) -> None:
        if self._pausado.is_set():
            return
        self._pausado.set()
        time.sleep(0.15)  # deixa o laço terminar o quadro em andamento
        self._fechar_segmento()
        self.sessao.log.registrar(self.item.tipo, "gravacao_pausada", {"item": self.item.numero})

    def retomar(self) -> None:
        if not self._pausado.is_set():
            return
        self.sessao.log.registrar(self.item.tipo, "gravacao_retomada", {"item": self.item.numero})
        self._pausado.clear()

    def parar_fontes(self) -> None:
        try:
            self._controle.stop()
        except Exception:
            pass
        try:
            self._som.parar()
        except Exception:
            pass

    def parar(self) -> None:
        if not self.ativo:
            return
        self.ativo = False
        self._parar.set()
        self._laco.join(timeout=10)
        self._fechar_segmento()
        self.parar_fontes()
        shutil.rmtree(self.pasta_temp, ignore_errors=True)
        self.sessao.log.registrar(self.item.tipo, "gravacao_encerrada", {
            "item": self.item.numero, "segmentos": self.segmentos,
            "tempo_gravado_s": round(self.tempo_gravado, 1)})


def monitores() -> list[dict]:
    """Monitores ligados, na ordem usada pelo Windows Graphics Capture (a partir de 1)."""
    import ctypes
    import ctypes.wintypes as w

    lista = []
    tipo = ctypes.WINFUNCTYPE(ctypes.c_int, w.HMONITOR, w.HDC, ctypes.POINTER(w.RECT), w.LPARAM)

    def coletar(hmon, hdc, retangulo, dado):
        r = retangulo.contents
        lista.append({"indice": len(lista) + 1, "largura": r.right - r.left, "altura": r.bottom - r.top,
                      "esquerda": r.left, "topo": r.top})
        return 1
    ctypes.windll.user32.EnumDisplayMonitors(None, None, tipo(coletar), 0)
    return lista
