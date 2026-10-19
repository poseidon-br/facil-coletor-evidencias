"""Sessão de coleta: pasta, log, numeração das evidências, abertura e fechamento.

O relatório é gerado só a partir do que está gravado na pasta (log, manifesto,
ambiente), nunca do estado em memória. Por isso tudo o que o relatório mostra
precisa passar por um evento do log.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

from .. import VERSAO
from . import ambiente as mod_ambiente
from . import carimbo, ferramenta, manifesto, tempo
from .hashing import sha256_arquivo, sha256_bytes
from .log import LogEncadeado, forma_canonica

PASTA_EVIDENCIAS = "Evidencias"
PASTA_VERIFICACAO = "Verificacao"
LIMITE_JUNTADA = 10 * 1024 * 1024  # 10 MB, limite do PJe e do eproc


def nome_seguro(texto: str) -> str:
    """Rótulo de arquivo sem espaços nem acentos, para não falhar no upload dos sistemas judiciais."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", sem_acento).strip("-").lower() or "arquivo"


class Item:
    def __init__(self, sessao: "Sessao", numero: str, tipo: str, descricao: str):
        self.sessao = sessao
        self.numero = numero
        self.tipo = tipo
        self.descricao = descricao
        self._contador = 0
        self._trava = threading.Lock()

    def proximo_arquivo(self, rotulo: str, extensao: str) -> Path:
        """Caminho do próximo arquivo gerado para este item: E-002_03_conversa.png"""
        with self._trava:
            self._contador += 1
            nome = f"{self.numero}_{self._contador:02d}_{nome_seguro(rotulo)}.{extensao.lstrip('.')}"
        return self.sessao.pasta / PASTA_EVIDENCIAS / nome

    @property
    def pasta_propria(self) -> Path:
        """Pasta para arquivos coletados que mantêm o nome original."""
        caminho = self.sessao.pasta / PASTA_EVIDENCIAS / self.numero
        caminho.mkdir(parents=True, exist_ok=True)
        return caminho


class Sessao:
    def __init__(self, pasta: Path, log: LogEncadeado, identificador: str):
        self.pasta = pasta
        self.log = log
        self.identificador = identificador
        self.itens: list[Item] = []
        self._trava = threading.Lock()
        self.encerrada = False
        self.hash_evento0: str | None = None

    # ------------------------------------------------------------------ abertura

    @classmethod
    def abrir(cls, pasta_base: Path, operador: str, qualificacao: str = "",
              referencia: str = "") -> "Sessao":
        pasta_base = Path(pasta_base)
        pasta_base.mkdir(parents=True, exist_ok=True)
        carimbo_local = datetime.now().strftime("%Y%m%d-%H%M%S")
        provisoria = pasta_base / f"COLETA_{carimbo_local}_abrindo"
        (provisoria / PASTA_VERIFICACAO).mkdir(parents=True)

        log = LogEncadeado(provisoria / PASTA_VERIFICACAO / "log.jsonl")
        evento0 = log.registrar("nucleo", "sessao_aberta", {
            "operador": operador.strip(),
            "qualificacao": qualificacao.strip(),
            "referencia": referencia.strip(),
            "versao": VERSAO,
        })
        identificador = f"{carimbo_local}-{evento0['hash'][:8]}"
        seq, ultimo = log.proximo_seq, log.ultimo_hash
        log.fechar()
        pasta = pasta_base / f"COLETA_{identificador}"
        provisoria.rename(pasta)
        (pasta / PASTA_EVIDENCIAS).mkdir()
        log = LogEncadeado(pasta / PASTA_VERIFICACAO / "log.jsonl", seq, ultimo)
        sessao = cls(pasta, log, identificador)
        log.registrar("nucleo", "identificador_definido", {
            "identificador": identificador,
            "regra": "data e hora local da abertura + 8 primeiros caracteres do hash do evento 0",
        })
        sessao._carimbo_abertura = forma_canonica(evento0)
        sessao.hash_evento0 = evento0["hash"]
        return sessao

    def preparar(self, componentes: dict | None = None) -> None:
        """Etapas automáticas da abertura. Podem levar alguns segundos (rede)."""
        info = ferramenta.identificar(componentes)
        (self.pasta / PASTA_VERIFICACAO / "ferramenta.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        self.log.registrar("nucleo", "ferramenta_verificada", {
            "versao": info["versao"], "commit": info["commit"], "oficial": info["oficial"],
            "motivo_nao_oficial": info["motivo_nao_oficial"], "hash_codigo": info["hash_codigo"],
            "python": info["python"], "componentes": info["componentes"],
            "hash_ferramenta_json": sha256_arquivo(self.pasta / PASTA_VERIFICACAO / "ferramenta.json"),
        })

        amb = mod_ambiente.registrar()
        caminho_amb = self.pasta / PASTA_VERIFICACAO / "ambiente.json"
        caminho_amb.write_text(json.dumps(amb, ensure_ascii=False, indent=1), encoding="utf-8")
        resumo = mod_ambiente.resumo(amb)
        self.log.registrar("nucleo", "ambiente_registrado",
                           {**resumo, "hash_ambiente_json": sha256_arquivo(caminho_amb)})
        if resumo["maquina_virtual"]:
            self.ocorrencia("O computador parece ser uma máquina virtual.", "alerta")
        if resumo["acesso_remoto"]:
            self.ocorrencia("Havia acesso remoto ativo ou programa de acesso remoto em execução.", "alerta")

        self.conferir_relogio()
        self._carimbar("abertura", self._carimbo_abertura)

    def conferir_relogio(self) -> None:
        resultados = tempo.consultar_ntp()
        mediana = tempo.diferenca_mediana_ms(resultados)
        self.log.registrar("nucleo", "relogio_conferido",
                           {"servidores": resultados, "diferenca_ms": mediana})
        if mediana is None:
            self.ocorrencia("Não foi possível consultar a hora oficial (sem acesso aos servidores de hora).",
                            "alerta")
        elif abs(mediana) > 2000:
            sentido = "atrasado" if mediana > 0 else "adiantado"
            segundos = f"{abs(mediana) / 1000:.1f}".replace(".", ",")
            self.ocorrencia(
                f"O relógio do computador estava {sentido} {segundos} s em relação à hora oficial. "
                "Os horários deste relatório são os do computador.", "alerta")

    def _carimbar(self, momento: str, dados: bytes) -> list[dict]:
        registros = carimbo.carimbar(dados, self.pasta / PASTA_VERIFICACAO / "carimbos", momento)
        obtidos = [r for r in registros if r.get("obtido")]
        self.log.registrar("nucleo", "carimbo", {"momento": momento, "hash_carimbado": sha256_bytes(dados),
                                                 "autoridades": registros, "obtidos": len(obtidos)})
        if not obtidos:
            self.ocorrencia(f"Carimbo do tempo de {momento} não obtido (sem acesso às autoridades de carimbo).",
                            "alerta")
        return registros

    # ------------------------------------------------------------------ durante

    def novo_item(self, tipo: str, descricao: str, dados: dict | None = None) -> Item:
        with self._trava:
            numero = f"E-{len(self.itens) + 1:03d}"
            item = Item(self, numero, tipo, descricao)
            self.itens.append(item)
        self.log.registrar(tipo, "item_iniciado",
                           {"item": numero, "tipo": tipo, "descricao": descricao, **(dados or {})})
        return item

    def encerrar_item(self, item: Item, dados: dict | None = None) -> None:
        self.log.registrar(item.tipo, "item_encerrado", {"item": item.numero, **(dados or {})})

    def relativo(self, caminho: Path) -> str:
        return Path(caminho).resolve().relative_to(self.pasta.resolve()).as_posix()

    def registrar_evidencia(self, item: Item, caminho: Path, papel: str, dados: dict | None = None,
                            sha256: str | None = None) -> dict:
        """Registra no log um arquivo gravado no pacote, com o hash calculado sobre a cópia no pacote."""
        caminho = Path(caminho)
        tamanho = caminho.stat().st_size
        registro = {"item": item.numero, "arquivo": self.relativo(caminho), "papel": papel,
                    "tamanho": tamanho, "sha256": sha256 or sha256_arquivo(caminho), **(dados or {})}
        self.log.registrar(item.tipo, "evidencia_registrada", registro)
        return registro

    def ocorrencia(self, descricao: str, gravidade: str = "informacao", item: str | None = None,
                   modulo: str = "nucleo") -> None:
        self.log.registrar(modulo, "ocorrencia",
                           {"descricao": descricao, "gravidade": gravidade, "item": item})

    # ------------------------------------------------------------------ fechamento

    def encerrar(self, gerar_relatorio=None) -> dict:
        """Fecha a sessão: manifesto, carimbo de fechamento, relatório e declaração."""
        self.encerrada = True
        self.log.registrar("nucleo", "sessao_encerrada",
                           {"itens": len(self.itens), "eventos": self.log.proximo_seq + 1})
        manifesto.escrever_leia_me(self.pasta)
        seq, ultimo = self.log.proximo_seq, self.log.ultimo_hash
        self.log.fechar()

        caminho_manifesto = manifesto.gerar(self.pasta, self.identificador, ultimo)
        # Eventos posteriores ao manifesto vão para um segundo arquivo, que continua a cadeia.
        self.log = LogEncadeado(self.pasta / PASTA_VERIFICACAO / "log_fechamento.jsonl", seq, ultimo)
        hash_manifesto = sha256_arquivo(caminho_manifesto)
        self.log.registrar("nucleo", "manifesto_gerado", {"sha256": hash_manifesto})
        self._carimbar("fechamento", caminho_manifesto.read_bytes())

        resultado = {"pasta": str(self.pasta), "hash_manifesto": hash_manifesto}
        if gerar_relatorio:
            resultado.update(gerar_relatorio(self.pasta, self.log))
        self.log.registrar("nucleo", "pacote_somente_leitura", {
            "aplicado_a": "todos os arquivos do pacote, exceto a declaração editável",
            "objetivo": "proteção contra alteração acidental; não impede alteração deliberada"})
        self.log.fechar()
        self._proteger_pacote()
        return resultado

    def _proteger_pacote(self) -> None:
        """Atributo somente leitura em todo o pacote, exceto a declaração, que é editável.

        Protege contra alteração acidental, não contra alteração deliberada; a
        prova de integridade continua sendo o manifesto com carimbo do tempo.
        """
        for caminho in self.pasta.rglob("*"):
            if caminho.is_file() and caminho.name != "Declaracao.docx":
                try:
                    caminho.chmod(0o444)
                except OSError:
                    pass
