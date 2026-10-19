"""Janela da ferramenta (pywebview): painel à esquerda, navegador à direita.

Os métodos da classe Api são chamados pelo JavaScript da tela; cada chamada
roda numa linha de execução própria e devolve o resultado como Promise.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path

import webview

from .. import NOME, NOME_COMPLETO, VERSAO, componentes
from ..nucleo.hashing import sha256_arquivo
from ..modulos import arquivo, eml, gravador, protecao_escrita, som
from ..modulos.navegador import ENDERECO_WHATSAPP, PASSOS_WHATSAPP, ColetaNavegador, _area_trabalho
from ..nucleo.sessao import Sessao
from ..relatorio import gerador

LARGURA_PAINEL = 440
TAMANHO_COMPACTO = (520, 800)


def geometria_compacta() -> tuple[int, int, int, int]:
    """Janela compacta, centralizada na área útil do monitor principal: x, y, largura, altura."""
    x, y, direita, baixo = _area_trabalho()
    largura = min(TAMANHO_COMPACTO[0], direita - x)
    altura = min(TAMANHO_COMPACTO[1], baixo - y - 40)
    return x + (direita - x - largura) // 2, y + (baixo - y - altura) // 2, largura, altura


def geometria_lateral() -> tuple[int, int, int, int]:
    """Coluna da esquerda, na altura total, para ficar ao lado do navegador."""
    x, y, _, baixo = _area_trabalho()
    return x, y, LARGURA_PAINEL, baixo - y
LINKS_AUTOR = {
    "site": "https://eliasedenis.com.br",
    "linkedin": "https://www.linkedin.com/in/pcedenis",
}
PASTA_WEB = Path(__file__).parent / "web"
PREFERENCIAS = Path(os.environ.get("LOCALAPPDATA", ".")) / "ColetorEvidencias" / "preferencias.json"


def _pasta_documentos() -> Path:
    buffer = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer)  # CSIDL_PERSONAL
    return Path(buffer.value or Path.home() / "Documents")


def _ler_preferencias() -> dict:
    try:
        return json.loads(PREFERENCIAS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _salvar_preferencias(dados: dict) -> None:
    PREFERENCIAS.parent.mkdir(parents=True, exist_ok=True)
    PREFERENCIAS.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


class Api:
    def __init__(self):
        self._janela = None
        self._sessao: Sessao | None = None
        self._navegador: ColetaNavegador | None = None
        self._gravacao_tela: gravador.Gravador | None = None
        self._item_tela = None
        self._itens: list[dict] = []
        self._som_testado = False
        self._resultado = None
        self._usb: dict | None = None
        self._trava = threading.Lock()

    # ------------------------------------------------------------ apoio

    def _js(self, codigo: str) -> None:
        try:
            self._janela.evaluate_js(codigo)
        except Exception:
            pass

    def _progresso(self, texto: str) -> None:
        self._js(f"progresso({json.dumps(texto)})")

    def _novo_item_tela(self, item, situacao="coletado") -> dict:
        registro = {"numero": item.numero, "tipo": item.tipo, "descricao": item.descricao, "situacao": situacao}
        self._itens.append(registro)
        return registro

    def _situacao(self, numero: str, situacao: str) -> None:
        for registro in self._itens:
            if registro["numero"] == numero:
                registro["situacao"] = situacao

    def _ocorrencias_recentes(self, desde_seq: int) -> list[str]:
        from ..nucleo.log import ler_eventos
        eventos = ler_eventos(self._sessao.pasta / "Verificacao" / "log.jsonl")
        return [e["dados"]["descricao"] for e in eventos
                if e["seq"] >= desde_seq and e["tipo"] == "ocorrencia" and e["dados"]["gravidade"] == "alerta"]

    # ------------------------------------------------------------ início

    def estado_inicial(self) -> dict:
        prefs = _ler_preferencias()
        return {"versao": VERSAO, "nome": NOME,
                "pasta": prefs.get("pasta") or str(_pasta_documentos() / "Coletas de Evidências"),
                "operador": prefs.get("operador", ""), "qualificacao": prefs.get("qualificacao", ""),
                "orgao": prefs.get("orgao", ""), "logomarca": prefs.get("logomarca", ""),
                "guia_visto": bool(prefs.get("guia_visto")),
                "protecao_pendente": bool(prefs.get("protecao_escrita_pendente"))
                                     and protecao_escrita.ler_valor() == 1,
                "componentes": {k: bool(v) for k, v in componentes.todos().items()}}

    def restaurar_protecao_pendente(self) -> dict:
        """Desativa um bloqueio de escrita que ficou ativo depois de uma coleta interrompida."""
        prefs = _ler_preferencias()
        pendente = prefs.get("protecao_escrita_pendente")
        if not pendente:
            return {"sucesso": True, "erro": None}
        resultado = protecao_escrita.restaurar(pendente.get("valor_anterior"))
        if resultado["sucesso"]:
            prefs.pop("protecao_escrita_pendente", None)
            _salvar_preferencias(prefs)
        return {"sucesso": resultado["sucesso"], "erro": resultado["erro"]}

    def concluir_guia(self, nao_mostrar: bool) -> None:
        _salvar_preferencias({**_ler_preferencias(), "guia_visto": bool(nao_mostrar)})

    def escolher_pasta(self) -> str | None:
        escolha = self._janela.create_file_dialog(webview.FileDialog.FOLDER)
        return escolha[0] if escolha else None

    def abrir_link(self, qual: str) -> None:
        """Abre no navegador padrão um dos endereços do autor (lista fixa, por clique do usuário)."""
        endereco = LINKS_AUTOR.get(qual)
        if endereco:
            webbrowser.open(endereco)

    def escolher_logomarca(self) -> str | None:
        escolha = self._janela.create_file_dialog(
            webview.FileDialog.OPEN, allow_multiple=False,
            file_types=("Imagens (*.png;*.jpg;*.jpeg)", "Todos os arquivos (*.*)"))
        return escolha[0] if escolha else None

    def iniciar(self, operador: str, qualificacao: str, referencia: str, pasta: str,
                guia: dict | None = None, orgao: str = "", logomarca: str = "") -> dict:
        if not operador.strip():
            raise ValueError("Informe o nome do operador.")
        _salvar_preferencias({**_ler_preferencias(), "pasta": pasta, "operador": operador.strip(),
                              "qualificacao": qualificacao.strip(), "orgao": orgao.strip(),
                              "logomarca": logomarca.strip()})
        self._sessao = Sessao.abrir(Path(pasta), operador, qualificacao, referencia)
        self._sessao.log.registrar("nucleo", "guia_inicial", {
            "mostrado": bool(guia and guia.get("mostrado")),
            "escolha_antivirus": (guia or {}).get("escolha_antivirus")})
        self._registrar_personalizacao(orgao.strip(), logomarca.strip())
        self._progresso("Conferindo a ferramenta, registrando o computador, consultando a hora oficial e "
                        "obtendo o carimbo do tempo de abertura...")
        self._sessao.preparar(componentes.todos())
        self._itens, self._som_testado, self._resultado = [], False, None
        return {"identificador": self._sessao.identificador, "pasta": str(self._sessao.pasta),
                "alertas": self._ocorrencias_recentes(0)}

    def _registrar_personalizacao(self, orgao: str, logomarca: str) -> None:
        """Copia a logomarca para o pacote e registra a personalização no log."""
        if not (orgao or logomarca):
            return
        dados = {"orgao": orgao or None, "logomarca": None, "sha256": None}
        origem = Path(logomarca) if logomarca else None
        if origem and origem.is_file() and origem.suffix.lower() in (".png", ".jpg", ".jpeg"):
            destino = self._sessao.pasta / "Verificacao" / f"logomarca{origem.suffix.lower()}"
            shutil.copyfile(origem, destino)
            dados["logomarca"] = self._sessao.relativo(destino)
            dados["sha256"] = sha256_arquivo(destino)
        elif logomarca:
            self._sessao.ocorrencia("A logomarca configurada não foi encontrada e o relatório sai sem ela.",
                                    "informacao")
        self._sessao.log.registrar("nucleo", "personalizacao", dados)

    # ------------------------------------------------------------ som

    def testar_som(self) -> dict:
        resultado = som.testar()
        if self._sessao:
            self._sessao.log.registrar("nucleo", "teste_som", resultado)
        self._som_testado = self._som_testado or resultado["captado"]
        return resultado

    # ------------------------------------------------------------ arquivos e e-mail

    def coletar_arquivos(self, modo: str) -> list[dict]:
        if modo == "pasta":
            escolha = self._janela.create_file_dialog(webview.FileDialog.FOLDER)
        else:
            escolha = self._janela.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True)
        if not escolha:
            return []
        novos = []
        for origem in escolha:
            self._progresso(f"Copiando e calculando hashes: {origem}")
            item = arquivo.coletar(self._sessao, origem,
                                   lambda i, n: self._progresso(f"Copiando {i} de {n}: {origem}"))
            novos.append(self._novo_item_tela(item))
        return novos

    def coletar_eml(self) -> list[dict]:
        escolha = self._janela.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
                                                 file_types=("Mensagens EML (*.eml)", "Todos os arquivos (*.*)"))
        novos = []
        for origem in escolha or []:
            self._progresso(f"Analisando {origem}")
            novos.append(self._novo_item_tela(eml.coletar(self._sessao, origem)))
        return novos

    # ------------------------------------------------------------ USB com bloqueio de escrita

    def ativar_protecao_usb(self) -> dict:
        resultado = protecao_escrita.ativar()
        self._usb = {"ativada": resultado["sucesso"], "valor_anterior": resultado["valor_anterior"],
                     "letra": None, "contexto": None}
        if resultado["sucesso"]:
            _salvar_preferencias({**_ler_preferencias(), "protecao_escrita_pendente":
                                  {"valor_anterior": resultado["valor_anterior"]}})
            self._sessao.log.registrar("arquivo", "protecao_escrita_ativada", {
                "valor_anterior": resultado["valor_anterior"], "valor_atual": resultado["valor_atual"],
                "metodo": protecao_escrita.METODO, "conferido_por_leitura": True})
        else:
            self._sessao.log.registrar("arquivo", "protecao_escrita_indisponivel", {
                "motivo": resultado["erro"] or "motivo desconhecido",
                "valor_atual": resultado["valor_atual"]})
            self._sessao.ocorrencia("O bloqueio de escrita não pôde ser ativado: "
                                    f"{resultado['erro'] or 'motivo desconhecido'}.", "alerta",
                                    None, "arquivo")
        return {"sucesso": resultado["sucesso"], "erro": resultado["erro"]}

    def seguir_sem_bloqueio_usb(self) -> None:
        self._usb = {"ativada": False, "valor_anterior": None, "letra": None, "contexto": None}
        self._sessao.log.registrar("arquivo", "protecao_escrita_indisponivel", {
            "motivo": "o operador optou por seguir sem o bloqueio",
            "valor_atual": protecao_escrita.ler_valor()})
        self._sessao.ocorrencia("A coleta de dispositivo USB seguiu sem o bloqueio de escrita, por escolha "
                                "do operador.", "alerta", None, "arquivo")

    def listar_volumes_usb(self) -> list[dict]:
        return protecao_escrita.volumes_usb()

    def registrar_dispositivo_usb(self, letra: str) -> dict:
        volume = arquivo._volume(Path(f"{letra}:\\"))
        protecao_ativa = protecao_escrita.ler_valor() == 1
        teste = protecao_escrita.testar_somente_leitura(letra) if protecao_ativa else None
        self._sessao.log.registrar("arquivo", "dispositivo_conectado", {
            "letra": letra, **volume, "protecao_ativa": protecao_ativa,
            "teste_somente_leitura": teste})
        self._usb = {**(self._usb or {"ativada": protecao_ativa, "valor_anterior": None}),
                     "letra": letra,
                     "contexto": {"ativa": protecao_ativa, "teste_somente_leitura": teste,
                                  "metodo": protecao_escrita.METODO}}
        return {"protecao_ativa": protecao_ativa, "teste_somente_leitura": teste, "volume": volume}

    def coletar_arquivos_usb(self, modo: str) -> list[dict]:
        letra = (self._usb or {}).get("letra")
        if not letra:
            raise RuntimeError("Escolha primeiro o dispositivo USB.")
        raiz = f"{letra}:\\"
        if modo == "pasta":
            escolha = self._janela.create_file_dialog(webview.FileDialog.FOLDER, directory=raiz)
        else:
            escolha = self._janela.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
                                                     directory=raiz)
        if not escolha:
            return []
        fora = [c for c in escolha if not str(c).upper().startswith(f"{letra.upper()}:")]
        if fora:
            raise ValueError(f"Escolha arquivos da unidade {letra}: (o dispositivo USB). "
                             f"Fora dela: {fora[0]}")
        novos = []
        for origem in escolha:
            self._progresso(f"Copiando e calculando hashes: {origem}")
            item = arquivo.coletar(self._sessao, origem,
                                   lambda i, n: self._progresso(f"Copiando {i} de {n}: {origem}"),
                                   contexto_usb=self._usb["contexto"])
            novos.append(self._novo_item_tela(item))
        return novos

    def restaurar_protecao_usb(self) -> dict:
        return self._restaurar_protecao()

    def _restaurar_protecao(self) -> dict:
        """Restaura o valor anterior do registro, confere relendo e limpa a pendência."""
        if not (self._usb and self._usb.get("ativada")):
            self._usb = None
            return {"sucesso": True, "erro": None}
        resultado = protecao_escrita.restaurar(self._usb.get("valor_anterior"))
        if self._sessao:
            self._sessao.log.registrar("arquivo", "protecao_escrita_restaurada", {
                "valor_restaurado": resultado["valor_restaurado"], "valor_atual": resultado["valor_atual"],
                "conferido_por_leitura": True, "sucesso": resultado["sucesso"]})
            if not resultado["sucesso"]:
                self._sessao.ocorrencia(
                    "O bloqueio de escrita por registro não foi desativado e continua valendo neste "
                    "computador: novos dispositivos USB conectados ficarão somente leitura até a "
                    "desativação. A ferramenta oferecerá a desativação na próxima abertura.",
                    "alerta", None, "arquivo")
        if resultado["sucesso"]:
            prefs = _ler_preferencias()
            prefs.pop("protecao_escrita_pendente", None)
            _salvar_preferencias(prefs)
            self._usb = None
        return {"sucesso": resultado["sucesso"], "erro": resultado["erro"]}

    # ------------------------------------------------------------ navegador

    def _posicionar(self, geometria: tuple[int, int, int, int]) -> None:
        x, y, largura, altura = geometria
        try:
            self._janela.resize(largura, altura)
            self._janela.move(x, y)
        except Exception:
            pass

    def _area_navegador(self) -> tuple[int, int, int, int]:
        x, y, direita, baixo = _area_trabalho()
        return x + LARGURA_PAINEL, y, direita, baixo

    def abrir_navegador(self, tipo: str, endereco: str = "") -> dict:
        if self._navegador or self._gravacao_tela:
            raise RuntimeError("Encerre o item em andamento antes de iniciar outro.")
        if tipo == "site":
            endereco = endereco.strip()
            if not endereco:
                raise ValueError("Informe o endereço do site.")
            if "://" not in endereco:
                endereco = "https://" + endereco
        else:
            endereco = ENDERECO_WHATSAPP
        seq = self._sessao.log.proximo_seq
        self._progresso("Abrindo o navegador protegido e iniciando a gravação...")
        self._posicionar(geometria_lateral())
        self._navegador = ColetaNavegador(self._sessao, tipo, endereco, self._area_navegador(),
                                         ao_terminar=self._navegador_terminou)
        try:
            item = self._navegador.abrir().result(timeout=120)
        except Exception:
            self._navegador = None
            self._posicionar(geometria_compacta())
            raise
        self._novo_item_tela(item, "em andamento")
        passos = []
        if tipo == "whatsapp":
            token = self._navegador.token or ""
            passos = [{"rotulo": r, "instrucao": t.replace("{token}", token),
                       "com_token": "{token}" in t, "token": token} for r, t in PASSOS_WHATSAPP]
        return {"numero": item.numero, "descricao": item.descricao, "passos": passos,
                "alertas": self._ocorrencias_recentes(seq)}

    def copiar_token(self) -> None:
        """Copia o token de verificação para a área de transferência do Windows."""
        if self._navegador and self._navegador.token:
            subprocess.run("clip", input=self._navegador.token.encode("ascii"),
                           check=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def _navegador_terminou(self, coleta: ColetaNavegador) -> None:
        if coleta.item:
            self._situacao(coleta.item.numero, "coletado")
        if self._navegador is coleta:
            self._navegador = None
            self._posicionar(geometria_compacta())
            self._js("itemTerminou()")

    def registrar_print(self, rotulo: str = "print", passo: int | None = None) -> dict:
        registro = self._navegador.registrar_print(rotulo or "print", passo).result(timeout=90)
        return {"arquivo": registro["arquivo"], "sha256": registro["sha256"]}

    def pular_passo(self, passo: int) -> None:
        self._navegador.pular_passo(passo).result(timeout=30)

    def pausar(self) -> None:
        if self._navegador:
            self._navegador.pausar().result(timeout=60)
        elif self._gravacao_tela:
            self._gravacao_tela.pausar()

    def retomar(self) -> None:
        if self._navegador:
            self._navegador.retomar().result(timeout=60)
        elif self._gravacao_tela:
            self._gravacao_tela.retomar()

    def encerrar_item(self) -> None:
        if self._navegador:
            coleta = self._navegador
            self._progresso("Encerrando a gravação e salvando o registro de tráfego...")
            coleta.encerrar()
            self._situacao(coleta.item.numero, "coletado")
            self._navegador = None
            self._posicionar(geometria_compacta())
        elif self._gravacao_tela:
            self._progresso("Encerrando a gravação...")
            self._gravacao_tela.parar()
            self._sessao.encerrar_item(self._item_tela)
            self._situacao(self._item_tela.numero, "coletado")
            self._gravacao_tela, self._item_tela = None, None

    # ------------------------------------------------------------ tela

    def monitores(self) -> list[dict]:
        return gravador.monitores()

    def gravar_tela(self, indice: int) -> dict:
        if self._navegador or self._gravacao_tela:
            raise RuntimeError("Encerre o item em andamento antes de iniciar outro.")
        self._item_tela = self._sessao.novo_item("tela", f"Monitor {indice}")
        self._gravacao_tela = gravador.Gravador(self._sessao, self._item_tela, monitor=indice,
                                               descricao_alvo=f"monitor {indice}")
        try:
            self._gravacao_tela.iniciar()
        except Exception as erro:
            self._sessao.ocorrencia(f"A gravação da tela não pôde começar: {erro}", "alerta",
                                   self._item_tela.numero, "tela")
            self._sessao.encerrar_item(self._item_tela)
            self._gravacao_tela = None
            raise
        return self._novo_item_tela(self._item_tela, "em andamento")

    # ------------------------------------------------------------ fechamento

    def encerrar_coleta(self) -> dict:
        self.encerrar_item()
        if self._usb and self._usb.get("ativada"):
            self._progresso("Desativando o bloqueio de escrita (o Windows vai pedir confirmação)...")
            self._restaurar_protecao()
        self._progresso("Gerando o manifesto e obtendo o carimbo do tempo de fechamento...")

        def gerar(pasta, log):
            self._progresso("Gerando o relatório em PDF e HTML e a declaração...")
            return gerador.gerar(pasta, log, componentes.chromium())
        self._resultado = self._sessao.encerrar(gerar)
        self._resultado["identificador"] = self._sessao.identificador
        self._sessao = None
        return self._resultado

    def abrir_pasta(self) -> None:
        if self._resultado:
            os.startfile(self._resultado["pasta"])

    def abrir_relatorio(self) -> None:
        if self._resultado:
            os.startfile(Path(self._resultado["pasta"]) / self._resultado["pdf"][0]["arquivo"])

    def ao_fechar(self) -> None:
        """Janela fechada no meio da coleta: encerra o navegador e as gravações."""
        if self._navegador:
            self._navegador.encerrar()
        if self._gravacao_tela:
            self._gravacao_tela.parar()
        if self._usb and self._usb.get("ativada"):
            self._restaurar_protecao()


def main() -> None:
    api = Api()
    x, y, largura, altura = geometria_compacta()
    janela = webview.create_window(
        f"{NOME_COMPLETO} {VERSAO}", url=str(PASTA_WEB / "index.html"), js_api=api,
        width=largura, height=altura, x=x, y=y, min_size=(380, 560),
        text_select=True)
    api._janela = janela

    def ao_tentar_fechar():
        """Só pergunta quando há coleta aberta; sem sessão, fecha direto."""
        if api._sessao is None:
            return True
        return janela.create_confirmation_dialog(
            f"{NOME} {VERSAO}", "Fechar a ferramenta? A coleta em andamento ficará sem relatório.")

    janela.events.closing += ao_tentar_fechar
    janela.events.closed += api.ao_fechar
    webview.start()


if __name__ == "__main__":
    main()
