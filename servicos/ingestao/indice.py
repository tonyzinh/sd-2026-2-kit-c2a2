"""
Indice persistente da ingestao.

- Guarda os itens em um arquivo JSON (volume compartilhado entre a API e o worker).
- adicionar() ACUMULA, deduplica pelo hash do texto, reajusta o TF-IDF sobre o
  corpus completo e recalcula TODOS os vetores (a dimensao muda com o vocabulario).
- Escrita atomica: grava em arquivo temporario e troca com os.replace(); um
  leitor nunca ve um arquivo pela metade.
- Lock de arquivo (O_EXCL) serializa o ciclo ler-modificar-gravar entre
  processos diferentes (API em modo sincrono + worker).
"""
import hashlib
import json
import logging
import os
import threading
import time
from contextlib import contextmanager

from servicos.comum.embeddings import Vetorizador

log = logging.getLogger("ingestao")


def hash_texto(texto):
    normalizado = " ".join(texto.split())
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()


class Indice:

    def __init__(self, caminho):
        self.caminho = caminho
        self._lock_arquivo = caminho + ".lock"
        self._lock = threading.Lock()
        self._itens = []
        self._assinatura = None
        self.vetorizador = Vetorizador()
        diretorio = os.path.dirname(os.path.abspath(caminho))
        os.makedirs(diretorio, exist_ok=True)
        self._recarregar_se_mudou()

    # ---- leitura -------------------------------------------------------
    def _assinatura_disco(self):
        try:
            st = os.stat(self.caminho)
            return (st.st_mtime_ns, st.st_size)
        except FileNotFoundError:
            return None

    def _recarregar_se_mudou(self):
        """Relê o arquivo se outro processo (worker) o alterou."""
        assinatura = self._assinatura_disco()
        if assinatura == self._assinatura:
            return
        if assinatura is None:
            self._itens, self._assinatura = [], None
            return
        for _ in range(5):  # Windows pode recusar leitura durante o replace
            try:
                with open(self.caminho, encoding="utf-8") as f:
                    self._itens = json.load(f)["itens"]
                self._assinatura = assinatura
                return
            except (PermissionError, json.JSONDecodeError):
                time.sleep(0.05)
        raise RuntimeError("nao foi possivel ler o indice")

    def itens(self):
        with self._lock:
            self._recarregar_se_mudou()
            return list(self._itens)

    def total(self):
        return len(self.itens())

    # ---- escrita -------------------------------------------------------
    @contextmanager
    def _trava(self, timeout=30.0):
        inicio = time.monotonic()
        while True:
            try:
                fd = os.open(self._lock_arquivo, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                try:  # lock abandonado por processo que morreu
                    if time.time() - os.path.getmtime(self._lock_arquivo) > 60:
                        os.remove(self._lock_arquivo)
                        continue
                except OSError:
                    pass
                if time.monotonic() - inicio > timeout:
                    raise TimeoutError("lock do indice ocupado")
                time.sleep(0.02)
        try:
            yield
        finally:
            try:
                os.remove(self._lock_arquivo)
            except OSError:
                pass

    def adicionar(self, docs):
        """docs: lista de {"texto","origem"}. Devolve {"novos","total"}."""
        with self._lock, self._trava():
            self._assinatura = None  # forca releitura sob o lock
            self._recarregar_se_mudou()
            existentes = {i["hash"] for i in self._itens}
            novos = []
            for d in docs:
                texto = d["texto"].strip()
                if not texto:
                    continue
                h = hash_texto(texto)
                if h in existentes:
                    continue
                existentes.add(h)
                novos.append({"texto": texto, "origem": d.get("origem", "desconhecida"),
                              "hash": h})
            if novos:
                itens = self._itens + novos
                # reajusta sobre o corpus completo e reindexa todos os itens
                try:
                    self.vetorizador.ajustar([i["texto"] for i in itens])
                    for i in itens:
                        i["vetor"] = self.vetorizador.vetorizar(i["texto"])
                except ValueError:  # vocabulario vazio (ex.: so tokens de 1 letra)
                    for i in itens:
                        i["vetor"] = []
                self._gravar(itens)
                self._itens = itens
                self._assinatura = self._assinatura_disco()
                log.info("indice: +%d novos (total=%d)", len(novos), len(itens))
            return {"novos": len(novos), "total": len(self._itens)}

    def _gravar(self, itens):
        tmp = f"{self.caminho}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"itens": itens}, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.caminho)

    def versao(self):
        """Identifica o conteudo atual (muda quando o corpus muda)."""
        h = hashlib.sha256()
        for i in self.itens():
            h.update(i["hash"].encode())
        return h.hexdigest()[:12]
