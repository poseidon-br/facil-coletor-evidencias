"""Registro de erros para depuração (erros.log), só local.

O arquivo fica na pasta "dados" da própria ferramenta (ver portatil.py) e nunca
sai dela por conta própria: o usuário o anexa, se quiser, ao relatar um problema. Não faz
parte da coleta nem do relatório. Guarda as falhas com o rastro do código
(traceback, a lista das funções em execução no momento do erro), os avisos,
os erros da tela e a sequência das ações acionadas na tela, sem os valores
digitados pelo usuário.
"""

from __future__ import annotations

import atexit
import faulthandler
import functools
import inspect
import json
import logging
import os
import platform
import sys
import threading
import time
from pathlib import Path

from . import NOME, VERSAO, portatil

LIMITE = 2 * 1024 * 1024  # acima disso, o arquivo vira erros.anterior.log na abertura seguinte
FORMATO = "%(asctime)s.%(msecs)03d %(levelname)s [%(threadName)s] %(name)s: %(message)s"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"
ARQUIVO_BUILD = Path(__file__).resolve().parents[1] / "build.json"

log = logging.getLogger("coletor")
_arquivo = None


def pasta() -> Path:
    """Pasta do erros.log, a mesma das preferências."""
    return portatil.pasta_dados()


def arquivo() -> Path:
    return pasta() / "erros.log"


def iniciar() -> Path | None:
    """Liga o registro em arquivo e as capturas de erros não tratados. Chamar antes de importar a interface."""
    global _arquivo
    sem_console = sys.stderr is None
    caminho, anterior = arquivo(), pasta() / "erros.anterior.log"
    try:
        pasta().mkdir(parents=True, exist_ok=True)
        if caminho.is_file() and caminho.stat().st_size > LIMITE:
            os.replace(caminho, anterior)
    except OSError:
        pass
    try:
        _arquivo = open(caminho, "a", encoding="utf-8", buffering=1)
    except OSError:
        _arquivo = None

    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    formato = logging.Formatter(FORMATO, FORMATO_DATA)
    if _arquivo:
        manipulador = logging.StreamHandler(_arquivo)
        manipulador.setFormatter(formato)
        raiz.addHandler(manipulador)
        # Falhas do próprio Python ou de bibliotecas nativas (captura de tela e som), que fecham o
        # programa sem passar pelo tratamento de erros, deixam ao menos o rastro no arquivo.
        faulthandler.enable(_arquivo)
    if sem_console:
        # Sem console (pythonw), o que as bibliotecas escrevem na saída de erro iria para lugar nenhum.
        sys.stderr = sys.stdout = _arquivo
    else:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formato)
        raiz.addHandler(console)

    # O pywebview só cria a própria saída no console quando o registro dele não tem destino; com este,
    # as mensagens dele seguem para o arquivo. O rastro que ele grava ao repassar um erro para a tela
    # já fica registrado por rastrear_chamadas, com o nome da ação.
    pywebview = logging.getLogger("pywebview")
    pywebview.addHandler(logging.NullHandler())
    pywebview.addFilter(lambda r: not str(r.msg).startswith("Traceback (most recent call last)"))

    sys.excepthook = _erro_nao_tratado
    threading.excepthook = _erro_em_linha
    atexit.register(lambda: log.info("%s encerrado", NOME))
    log.info("%s %s iniciado | %s", NOME, VERSAO, _ambiente())
    log.info("dados em %s (%s)", pasta(), "portátil, na pasta da ferramenta" if portatil.portatil()
             else "perfil do usuário, porque a pasta da ferramenta não aceita gravação")
    return caminho if _arquivo else None


def preparar_janela() -> None:
    """Libera as bibliotecas .NET marcadas como baixadas da internet, que impediriam a janela de abrir."""
    liberados = portatil.liberar_bibliotecas_dotnet()
    if liberados:
        log.info("marca de origem da internet retirada de %d bibliotecas .NET do pacote", len(liberados))


def avisar_falha_abertura() -> None:
    """Janela que não abriu: avisa o usuário e oferece a pasta do erros.log, em vez de fechar em silêncio."""
    import ctypes
    texto = (f"O {NOME} não conseguiu abrir.\n\nO motivo ficou registrado no arquivo erros.log, na pasta:\n"
             f"{pasta()}\n\nEnvie esse arquivo a quem lhe passou a ferramenta.\n\nAbrir a pasta agora?")
    try:
        # 0x4 = botões Sim e Não; 0x30 = ícone de aviso; 6 = Sim
        if ctypes.windll.user32.MessageBoxW(None, texto, f"{NOME} {VERSAO}", 0x4 | 0x30) == 6:
            os.startfile(pasta())
    except Exception:
        pass


def _ambiente() -> str:
    try:
        commit = json.loads(ARQUIVO_BUILD.read_text(encoding="utf-8")).get("commit", "")[:12]
        origem = f"pacote, commit {commit}"
    except Exception:
        origem = "desenvolvimento"
    return (f"{origem} | Windows {platform.release()} {platform.version()} {platform.machine()} | "
            f"Python {platform.python_version()}")


def _erro_nao_tratado(tipo, valor, rastro) -> None:
    if issubclass(tipo, KeyboardInterrupt):
        sys.__excepthook__(tipo, valor, rastro)
        return
    log.critical("Erro não tratado", exc_info=(tipo, valor, rastro))


def _erro_em_linha(args) -> None:
    if args.exc_type is SystemExit:
        return
    nome = args.thread.name if args.thread else "desconhecida"
    log.critical("Erro não tratado na linha de execução %s", nome,
                 exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def rastrear_chamadas(sem_registro: tuple[str, ...] = ()):
    """Decorador da classe Api: registra cada ação chamada pela tela (só o nome, sem os valores) e as falhas.

    A assinatura de cada método é preservada, porque o pywebview a lê para montar as funções da tela.
    """
    def decorar(classe):
        for nome, funcao in list(vars(classe).items()):
            if nome.startswith("_") or not inspect.isfunction(funcao):
                continue
            setattr(classe, nome, _rastreado(nome, funcao, nome not in sem_registro))
        return classe
    return decorar


def _rastreado(nome: str, funcao, registrar_inicio: bool):
    @functools.wraps(funcao)
    def chamada(*args, **kwargs):
        inicio = time.monotonic()
        if registrar_inicio:
            log.info("ação: %s", nome)
        try:
            return funcao(*args, **kwargs)
        except Exception:
            log.error("ação %s falhou após %.1f s", nome, time.monotonic() - inicio, exc_info=True)
            raise
    chamada.__signature__ = inspect.signature(funcao)
    return chamada
