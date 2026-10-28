"""
Circuit breaker - baseado no modelo de referencia, com as melhorias:

  - threading.Lock: o uvicorn atende requisicoes em varias threads;
  - estado `meio`: apenas UMA chamada de teste (sonda) passa; as demais sao
    recusadas com CircuitoAberto enquanto a sonda nao termina;
  - log a cada transicao de estado;
  - status() para expor o estado em /saude.

Estados:
  fechado  -> deixa passar (normal)
  aberto   -> recusa na hora, sem tentar (servico esta quebrado)
  meio     -> deixa passar UMA chamada de teste para ver se voltou
"""
import logging
import threading
import time

log = logging.getLogger("disjuntor")


class CircuitoAberto(Exception):
    """Levantada quando o disjuntor esta aberto e recusa a chamada."""

    def __init__(self, mensagem="disjuntor aberto: chamada recusada", retry_apos=0.0):
        super().__init__(mensagem)
        self.retry_apos = retry_apos


class CircuitBreaker:

    def __init__(self, limite_falhas=5, espera_segundos=30, nome="llm", relogio=time.monotonic):
        self.limite_falhas = limite_falhas
        self.espera_segundos = espera_segundos
        self.nome = nome
        self._relogio = relogio
        self._lock = threading.Lock()
        self.falhas = 0
        self.estado = "fechado"
        self.aberto_em = 0.0
        self._sonda_em_andamento = False

    def _transicao(self, novo):
        if novo != self.estado:
            log.warning("disjuntor[%s]: %s -> %s (falhas=%d)",
                        self.nome, self.estado, novo, self.falhas)
            self.estado = novo

    def _restante(self):
        return max(0.0, self.espera_segundos - (self._relogio() - self.aberto_em))

    def chamar(self, funcao, *args, **kwargs):
        with self._lock:
            sonda = False
            if self.estado == "aberto":
                restante = self._restante()
                if restante > 0:
                    raise CircuitoAberto("disjuntor aberto: chamada recusada", restante)
                self._transicao("meio")
            if self.estado == "meio":
                if self._sonda_em_andamento:
                    raise CircuitoAberto("disjuntor em teste (meio): aguarde", 1.0)
                self._sonda_em_andamento = True
                sonda = True
        try:
            resultado = funcao(*args, **kwargs)
        except Exception:
            self._registrar_falha(sonda)
            raise
        self._registrar_sucesso(sonda)
        return resultado

    def _registrar_falha(self, sonda):
        with self._lock:
            if sonda:
                self._sonda_em_andamento = False
            self.falhas += 1
            if self.falhas >= self.limite_falhas or self.estado == "meio":
                self.aberto_em = self._relogio()
                self._transicao("aberto")

    def _registrar_sucesso(self, sonda):
        with self._lock:
            if sonda:
                self._sonda_em_andamento = False
            self.falhas = 0
            self._transicao("fechado")

    def status(self):
        with self._lock:
            return {"estado": self.estado, "falhas": self.falhas,
                    "limite_falhas": self.limite_falhas,
                    "espera_segundos": self.espera_segundos,
                    "reabre_em_segundos": round(self._restante(), 1)
                    if self.estado == "aberto" else 0.0}
