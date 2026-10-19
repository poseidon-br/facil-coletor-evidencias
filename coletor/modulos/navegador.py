"""Navegador controlado para coleta de site e de WhatsApp Web.

Cada item abre um navegador novo, com perfil vazio e sem extensões, controlado
por canal interno (pipe). Registra cada página com IP e certificado, prints,
downloads, abas, diálogos e o tráfego completo (HAR). Vigia a abertura das
ferramentas de desenvolvedor (DevTools), fechando-as de imediato, e grava a
janela inteira com som.

O DevTools não pode ser bloqueado de antemão: testado em 14/10/2026, a
configuração que o desliga também desliga o canal interno pelo qual a
ferramenta controla o navegador, e a política equivalente no registro do
Windows exige administrador.

O Playwright exige que todas as chamadas ocorram na mesma linha de execução;
por isso os comandos da interface passam por uma fila.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import queue
import threading
import time
import zipfile
from concurrent.futures import Future
from pathlib import Path
from urllib.parse import urlsplit

import psutil

from .. import componentes
from ..nucleo.sessao import Item, Sessao
from . import certificado, token as mod_token
from .gravador import Gravador

ENDERECO_WHATSAPP = "https://web.whatsapp.com/"

# Domínios de onde antivírus conhecidos injetam scripts nas páginas exibidas.
INJECAO_CONHECIDA = {
    "kaspersky-labs.com": "Kaspersky",
    "kis.v2.scr.kaspersky-labs.com": "Kaspersky",
    "avast.com": "Avast",
    "avg.com": "AVG",
    "bitdefender.net": "Bitdefender",
    "eset.com": "ESET",
    "norton.com": "Norton",
}

# O espaço {token} do passo de envio é preenchido com o token de verificação da sessão.
PASSOS_WHATSAPP = [
    ("Identificação da conta",
     "Abra o seu perfil (clique na sua foto, no alto à esquerda) e deixe o seu número de telefone "
     "visível: ele precisa aparecer no print. Depois clique em Registrar."),
    ("Identificação do contato",
     "Abra a conversa e clique no nome do contato ou do grupo, no alto, e deixe visível o número de "
     "telefone do contato ou a lista de participantes: o número precisa aparecer no print. Depois "
     "clique em Registrar."),
    ("Envio do token de verificação",
     "A ferramenta gerou o código {token} para esta coleta. Abra a conversa com você mesmo (procure "
     "pelo seu nome ou por \"Você\" na busca do WhatsApp), digite ou cole o código exatamente como "
     "exibido e envie a mensagem. Quando ela aparecer na conversa, clique em Registrar."),
]


def _area_trabalho() -> tuple[int, int, int, int]:
    """Área útil do monitor principal (sem a barra de tarefas)."""
    r = wt.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
    return r.left, r.top, r.right, r.bottom


def _janelas_do_executavel(caminho_exe: str) -> list[int]:
    alvo = os.path.normcase(os.path.realpath(caminho_exe))
    pids = set()
    for proc in psutil.process_iter(["pid", "exe"]):
        exe = proc.info["exe"]
        if exe and os.path.normcase(os.path.realpath(exe)) == alvo:
            pids.add(proc.info["pid"])
    janelas = []
    tipo = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def coletar(hwnd, _):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        pid = wt.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        classe = ctypes.create_unicode_buffer(64)
        ctypes.windll.user32.GetClassNameW(hwnd, classe, 64)
        if pid.value in pids and classe.value == "Chrome_WidgetWin_1" \
                and ctypes.windll.user32.GetWindowTextLengthW(hwnd) > 0:
            janelas.append(hwnd)
        return True
    ctypes.windll.user32.EnumWindows(tipo(coletar), 0)
    return janelas


def _modulos_estranhos(caminho_exe: str) -> dict:
    """Bibliotecas carregadas no navegador que não são do Windows nem do próprio navegador."""
    pasta_navegador = os.path.normcase(os.path.dirname(os.path.realpath(caminho_exe)))
    pasta_windows = os.path.normcase(os.environ.get("SystemRoot", r"C:\Windows"))
    alvo = os.path.normcase(os.path.realpath(caminho_exe))
    estranhos, total = set(), 0
    for proc in psutil.process_iter(["pid", "exe"]):
        exe = proc.info["exe"]
        if not exe or os.path.normcase(os.path.realpath(exe)) != alvo:
            continue
        try:
            for mapa in proc.memory_maps():
                caminho = os.path.normcase(mapa.path)
                if not caminho.endswith(".dll"):
                    continue
                total += 1
                if not (caminho.startswith(pasta_navegador) or caminho.startswith(pasta_windows)):
                    estranhos.add(mapa.path)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return {"estranhos": sorted(estranhos), "bibliotecas_examinadas": total}


class ColetaNavegador:
    """Um item de site ou de WhatsApp Web."""

    def __init__(self, sessao: Sessao, tipo: str, endereco: str, area: tuple[int, int, int, int] | None = None,
                 ao_terminar=None):
        self.sessao = sessao
        self.tipo = tipo
        self.endereco = endereco
        self.area = area
        self.ao_terminar = ao_terminar
        self.item: Item | None = None
        self.gravador: Gravador | None = None
        self.passos = list(PASSOS_WHATSAPP) if tipo == "whatsapp" else []
        self.token: str | None = None
        self._fila: queue.Queue = queue.Queue()
        self._fim = threading.Event()
        self._encerrado = threading.Event()
        self._pendentes: dict = {}
        self._ultimo_endereco: dict = {}
        self._primeira_navegacao = True
        self._preparadas: dict = {}
        self._abas_vistas = 0
        self._hosts_interceptados: set = set()
        self._exe = componentes.chromium()

    # ================================================================ interface pública

    def abrir(self, tempo_limite: float = 90) -> Future:
        pronto: Future = Future()
        threading.Thread(target=self._executar, args=(pronto,), daemon=True).start()
        return pronto

    def _comando(self, funcao, *args) -> Future:
        futuro: Future = Future()
        if self._fim.is_set():
            futuro.set_exception(RuntimeError("o navegador já foi encerrado"))
        else:
            self._fila.put((funcao, args, futuro))
        return futuro

    def registrar_print(self, rotulo: str = "print", passo: int | None = None) -> Future:
        return self._comando(self._print, rotulo, passo)

    def pular_passo(self, passo: int) -> Future:
        return self._comando(self._pular, passo)

    def pausar(self) -> Future:
        return self._comando(lambda: self.gravador and self.gravador.pausar())

    def retomar(self) -> Future:
        return self._comando(lambda: self.gravador and self.gravador.retomar())

    def encerrar(self) -> None:
        """Encerra o item e espera a finalização (gravação, HAR, registro)."""
        if not self._fim.is_set():
            self._fim.set()
        self._encerrado.wait(timeout=180)

    # ================================================================ linha de execução própria

    def _executar(self, pronto: Future) -> None:
        from playwright.sync_api import sync_playwright

        descricao = (urlsplit(self.endereco).hostname or self.endereco) if self.tipo == "site" else "WhatsApp Web"
        self.item = self.sessao.novo_item(self.tipo, descricao, {"endereco_digitado": self.endereco})
        if self.tipo == "whatsapp" and self.sessao.hash_evento0:
            self.token = mod_token.derivar(self.sessao.hash_evento0)
            self.sessao.log.registrar(self.tipo, "token_gerado", {
                "item": self.item.numero, "token": self.token, "derivacao": mod_token.DERIVACAO,
                "enviado_para": "conversa do próprio operador no WhatsApp"})
        pasta_rede = self.sessao.pasta / "Verificacao" / "rede"
        pasta_rede.mkdir(parents=True, exist_ok=True)
        self._har = pasta_rede / f"{self.item.numero}.har.zip"
        try:
            with sync_playwright() as p:
                try:
                    self._iniciar(p)
                except Exception as erro:
                    self.sessao.ocorrencia(f"Não foi possível abrir o navegador: {erro}", "alerta",
                                           self.item.numero, self.tipo)
                    self._fim.set()
                    self._fechar_apos_falha()
                    pronto.set_exception(RuntimeError(f"Não foi possível abrir o navegador: {erro}"))
                    return
                pronto.set_result(self.item)
                self._laco()
                self._finalizar()
        except Exception as erro:
            if not pronto.done():
                pronto.set_exception(erro)
            self.sessao.ocorrencia(f"Falha no navegador: {erro}", "alerta", self.item.numero, self.tipo)
        finally:
            self.sessao.encerrar_item(self.item, {"motivo": "encerrado"})
            self._encerrado.set()
            if self.ao_terminar:
                self.ao_terminar(self)

    def _fechar_apos_falha(self) -> None:
        for objeto in (getattr(self, "gravador", None), getattr(self, "navegador", None)):
            try:
                objeto and (objeto.parar() if objeto is self.gravador else objeto.close())
            except Exception:
                pass

    def _iniciar(self, p) -> None:
        args = ["--no-first-run", "--no-default-browser-check", "--lang=pt-BR"]
        if self.area:
            x, y, direita, baixo = self.area
            args += [f"--window-position={x},{y}", f"--window-size={direita - x},{baixo - y}"]
        antes = set(_janelas_do_executavel(self._exe)) if self._exe else set()
        self.navegador = p.chromium.launch(headless=False, executable_path=self._exe, args=args)

        # Vigilância das ferramentas de desenvolvedor pelo canal interno.
        self._cdp_navegador = self.navegador.new_browser_cdp_session()
        self._cdp_navegador.on("Target.targetCreated", self._ao_ver_alvo)
        self._cdp_navegador.on("Target.targetInfoChanged", self._ao_ver_alvo)
        self._cdp_navegador.send("Target.setDiscoverTargets", {"discover": True})

        self.sessao.log.registrar(self.tipo, "protecao_navegador", {
            "item": self.item.numero, "versao_navegador": self.navegador.version,
            "devtools": "vigiado e fechado de imediato se aberto", "canal_controle": "pipe",
            "extensoes": "desativadas", "perfil": "novo, apagado ao final"})

        self.contexto = self.navegador.new_context(
            no_viewport=True, accept_downloads=True, locale="pt-BR",
            record_har_path=str(self._har), record_har_content="attach")
        self.contexto.on("page", self._preparar_pagina)
        self.pagina = self.contexto.new_page()
        self._preparar_pagina(self.pagina)
        self._esperar_canal(self.pagina)

        hwnd = self._localizar_janela(antes)
        modulos = _modulos_estranhos(self._exe) if self._exe else {"estranhos": [], "bibliotecas_examinadas": 0}
        self.sessao.log.registrar(self.tipo, "modulos_navegador", {"item": self.item.numero, "momento": "abertura",
                                                                   **modulos})
        if modulos["estranhos"]:
            self.sessao.ocorrencia(
                f"Bibliotecas de outros programas carregadas no navegador: {', '.join(modulos['estranhos'][:5])}",
                "alerta", self.item.numero, self.tipo)

        if hwnd:
            self.gravador = Gravador(self.sessao, self.item, hwnd=hwnd, descricao_alvo="janela do navegador")
            try:
                self.gravador.iniciar()
            except Exception as erro:
                self.gravador = None
                self.sessao.ocorrencia(f"A gravação da janela não pôde começar: {erro}", "alerta",
                                       self.item.numero, self.tipo)
        else:
            self.sessao.ocorrencia("A janela do navegador não foi localizada; a gravação não começou.",
                                   "alerta", self.item.numero, self.tipo)

        try:
            self.pagina.goto(self.endereco, wait_until="domcontentloaded", timeout=60000)
        except Exception as erro:
            self.sessao.ocorrencia(f"O endereço não carregou completamente: {erro}", "informacao",
                                   self.item.numero, self.tipo)

    def _esperar_canal(self, pagina, limite: float = 10) -> None:
        """O certificado completo só fica disponível para páginas carregadas com o canal já ligado."""
        chave = id(getattr(pagina, "_impl_obj", pagina))
        fim = time.monotonic() + limite
        while self._preparadas.get(chave) is None and time.monotonic() < fim:
            pagina.wait_for_timeout(50)

    def _localizar_janela(self, antes: set) -> int | None:
        if not self._exe:
            return None
        limite = time.monotonic() + 10
        while time.monotonic() < limite:
            novas = [h for h in _janelas_do_executavel(self._exe) if h not in antes]
            if novas:
                return novas[0]
            self.pagina.wait_for_timeout(200)
        return None

    def _laco(self) -> None:
        while not self._fim.is_set():
            try:
                funcao, args, futuro = self._fila.get_nowait()
            except queue.Empty:
                paginas = [pg for pg in self.contexto.pages if not pg.is_closed()]
                if not paginas or not self.navegador.is_connected():
                    self.sessao.ocorrencia("O navegador foi fechado pelo operador antes de encerrar o item.",
                                           "informacao", self.item.numero, self.tipo)
                    break
                try:
                    paginas[-1].wait_for_timeout(100)  # deixa o Playwright entregar os eventos
                except Exception:
                    time.sleep(0.1)
                continue
            try:
                futuro.set_result(funcao(*args))
            except Exception as erro:
                futuro.set_exception(erro)
        self._fim.set()
        while not self._fila.empty():
            _, _, futuro = self._fila.get_nowait()
            futuro.set_exception(RuntimeError("o navegador já foi encerrado"))

    def _finalizar(self) -> None:
        for pagina in list(self._pendentes):
            self._registrar_navegacao(pagina)
        if self.gravador:
            self.gravador.parar()
        try:
            modulos = _modulos_estranhos(self._exe) if self._exe else None
            if modulos:
                self.sessao.log.registrar(self.tipo, "modulos_navegador",
                                          {"item": self.item.numero, "momento": "encerramento", **modulos})
        except Exception:
            pass
        try:
            self.contexto.close()
        except Exception:
            pass
        try:
            self.navegador.close()
        except Exception:
            pass
        if self._har.is_file():
            requisicoes, dominios = self._resumo_har()
            self.sessao.registrar_evidencia(self.item, self._har, "har",
                                            {"requisicoes": requisicoes, "dominios": dominios})
            injetores = sorted({nome for d in dominios for sufixo, nome in INJECAO_CONHECIDA.items()
                                if d == sufixo or d.endswith("." + sufixo)})
            if injetores and self.tipo == "site":
                self.sessao.ocorrencia(
                    f"As páginas carregaram conteúdo de servidores do antivírus {', '.join(injetores)}, o que "
                    "indica que o antivírus inseriu código nas páginas exibidas. O conteúdo original entregue "
                    "pelo site está no registro de tráfego (HAR).", "alerta", self.item.numero, self.tipo)
        else:
            self.sessao.ocorrencia("O registro de tráfego (HAR) não foi gravado.", "alerta",
                                   self.item.numero, self.tipo)

    def _resumo_har(self) -> tuple[int, list[str]]:
        with zipfile.ZipFile(self._har) as z:
            nome = next(n for n in z.namelist() if n.endswith(".har"))
            har = json.loads(z.read(nome))
        entradas = har["log"]["entries"]
        dominios = sorted({urlsplit(e["request"]["url"]).hostname or "" for e in entradas} - {""})
        return len(entradas), dominios

    # ================================================================ eventos do navegador

    def _ao_ver_alvo(self, evento: dict) -> None:
        info = evento.get("targetInfo", {})
        if not info.get("url", "").startswith("devtools://"):
            return
        try:
            self._cdp_navegador.send("Target.closeTarget", {"targetId": info["targetId"]})
            acao = "fechado pela ferramenta"
        except Exception:
            acao = "não foi possível fechar"
        self.sessao.log.registrar(self.tipo, "devtools_detectado",
                                  {"item": self.item.numero, "acao": acao})
        self.sessao.ocorrencia(f"As ferramentas de desenvolvedor (DevTools) foram abertas e {acao}.",
                               "alerta", self.item.numero, self.tipo)

    def _preparar_pagina(self, pagina) -> None:
        chave = id(getattr(pagina, "_impl_obj", pagina))
        if chave in self._preparadas:
            return
        # Marca e instala os acompanhamentos antes de qualquer espera: enquanto o canal
        # interno abre, o Playwright entrega outros eventos, inclusive o desta mesma aba.
        self._preparadas[chave] = None
        pagina.on("response", lambda r: self._ao_responder(pagina, r))
        pagina.on("load", lambda: self._registrar_navegacao(pagina))
        pagina.on("framenavigated", lambda f: self._ao_navegar(pagina, f))
        pagina.on("download", self._ao_baixar)
        pagina.on("dialog", self._ao_dialogo)
        pagina.on("close", lambda: self.sessao.log.registrar(
            self.tipo, "aba", {"item": self.item.numero, "acao": "fechada", "endereco": pagina.url}))
        if self._abas_vistas:
            self.sessao.log.registrar(self.tipo, "aba", {"item": self.item.numero, "acao": "aberta",
                                                        "endereco": pagina.url})
        self._abas_vistas += 1
        try:
            cdp = self.contexto.new_cdp_session(pagina)
            cdp.send("Network.enable")
            self._preparadas[chave] = cdp
        except Exception:
            pass  # sem o canal, o certificado vem do resumo fornecido pelo Playwright

    def _ao_responder(self, pagina, resposta) -> None:
        try:
            if not (resposta.request.is_navigation_request() and resposta.frame == pagina.main_frame):
                return
        except Exception:
            return
        if pagina in self._pendentes:
            self._registrar_navegacao(pagina)
        dados = {"item": self.item.numero, "endereco_final": resposta.url,
                 "codigo_resposta": resposta.status, "ip": None, "porta": None, "certificado": None}
        if self._primeira_navegacao:
            dados["endereco_digitado"] = self.endereco
            self._primeira_navegacao = False
        try:
            servidor = resposta.server_addr() or {}
            dados["ip"], dados["porta"] = servidor.get("ipAddress"), servidor.get("port")
        except Exception:
            pass
        if resposta.url.startswith("https://"):
            try:
                dados["_resumo_seguranca"] = resposta.security_details() or {}
            except Exception:
                dados["_resumo_seguranca"] = {}
        self._pendentes[pagina] = dados

    def _certificado(self, pagina, endereco: str, resumo: dict) -> dict | None:
        """Cadeia completa pelo canal interno; se indisponível, o resumo do Playwright."""
        partes = urlsplit(endereco)
        origem = f"{partes.scheme}://{partes.netloc}"
        chave = id(getattr(pagina, "_impl_obj", pagina))
        try:
            cdp = self._preparadas.get(chave)
            if cdp is None:
                cdp = self._preparadas[chave] = self.contexto.new_cdp_session(pagina)
                cdp.send("Network.enable")
            cadeia = cdp.send("Network.getCertificate", {"origin": origem})["tableNames"]
            return certificado.analisar_cadeia(cadeia)
        except Exception:
            if not resumo:
                return None
            return {"emitido_para": resumo.get("subjectName"), "emitido_por": resumo.get("issuer"),
                    "autoridade_raiz": None, "raiz_publica": None, "valido_ate": resumo.get("validTo")}

    def _registrar_navegacao(self, pagina) -> None:
        dados = self._pendentes.pop(pagina, None)
        if not dados:
            return
        resumo = dados.pop("_resumo_seguranca", None)
        if resumo is not None:
            dados["certificado"] = self._certificado(pagina, dados["endereco_final"], resumo)
        try:
            dados["titulo"] = pagina.title()
        except Exception:
            dados["titulo"] = None
        self._ultimo_endereco[pagina] = dados["endereco_final"]
        self.sessao.log.registrar(self.tipo, "navegacao", dados)
        cert = dados.get("certificado")
        host = urlsplit(dados["endereco_final"]).hostname
        if cert and cert.get("raiz_publica") is False and host not in self._hosts_interceptados:
            self._hosts_interceptados.add(host)
            self.sessao.ocorrencia(
                f"A conexão segura com {host} foi intermediada por "
                f"\"{cert['autoridade_raiz']}\", autoridade instalada neste computador e que não consta da "
                "lista pública de autoridades reconhecidas. Isso costuma indicar antivírus ou proxy que "
                "inspeciona conexões seguras; o certificado original do site não pôde ser conferido.",
                "alerta", self.item.numero, self.tipo)

    def _ao_navegar(self, pagina, quadro) -> None:
        if quadro != pagina.main_frame or pagina in self._pendentes:
            return
        if quadro.url != self._ultimo_endereco.get(pagina) and quadro.url != "about:blank":
            self._ultimo_endereco[pagina] = quadro.url
            self.sessao.log.registrar(self.tipo, "pagina", {"item": self.item.numero, "endereco": quadro.url})

    def _ao_baixar(self, download) -> None:
        nome = download.suggested_filename or "arquivo"
        extensao = Path(nome).suffix.lstrip(".") or "bin"
        destino = self.item.proximo_arquivo("download " + Path(nome).stem, extensao)
        try:
            download.save_as(str(destino))
            self.sessao.registrar_evidencia(self.item, destino, "download",
                                            {"endereco_origem": download.url, "nome_sugerido": nome})
        except Exception as erro:
            self.sessao.ocorrencia(f"Falha ao salvar o download {nome}: {erro}", "alerta",
                                   self.item.numero, self.tipo)

    def _ao_dialogo(self, dialogo) -> None:
        resposta = "aceito" if dialogo.type == "alert" else "recusado"
        self.sessao.log.registrar(self.tipo, "dialogo", {"item": self.item.numero, "tipo": dialogo.type,
                                                         "mensagem": dialogo.message[:500], "resposta": resposta})
        try:
            dialogo.accept() if dialogo.type == "alert" else dialogo.dismiss()
        except Exception:
            pass

    # ================================================================ comandos

    def _pagina_atual(self):
        paginas = [pg for pg in self.contexto.pages if not pg.is_closed()]
        return paginas[-1] if paginas else None

    def _print(self, rotulo: str, passo: int | None) -> dict:
        pagina = self._pagina_atual()
        if pagina is None:
            raise RuntimeError("nenhuma página aberta")
        destino = self.item.proximo_arquivo(rotulo, "png")
        pagina.screenshot(path=str(destino), full_page=(self.tipo == "site"), timeout=60000)
        registro = self.sessao.registrar_evidencia(self.item, destino, "print", {
            "rotulo": rotulo, "endereco": pagina.url, "titulo": pagina.title(),
            "pagina_inteira": self.tipo == "site"})
        if passo is not None:
            self.sessao.log.registrar(self.tipo, "identificacao_passo", {
                "item": self.item.numero, "passo": passo, "rotulo": rotulo,
                "arquivo": registro["arquivo"], "pulado": False})
        return registro

    def _pular(self, passo: int) -> None:
        rotulo = self.passos[passo - 1][0] if 0 < passo <= len(self.passos) else f"passo {passo}"
        self.sessao.log.registrar(self.tipo, "identificacao_passo", {
            "item": self.item.numero, "passo": passo, "rotulo": rotulo, "arquivo": None, "pulado": True})
        self.sessao.ocorrencia(f"O passo \"{rotulo}\" do roteiro de identificação foi pulado.", "alerta",
                               self.item.numero, self.tipo)
