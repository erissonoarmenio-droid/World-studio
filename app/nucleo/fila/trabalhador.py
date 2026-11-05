"""O trabalhador da fila (tarefa 10). Roda dentro do servidor (decisão de Eri, 25/10).

Ciclo: devolve travados → pega o próximo (FOR UPDATE SKIP LOCKED, então dois
trabalhadores nunca pegam o mesmo) → executa FORA da transação → conclui ou falha.

- Falhou: tenta de novo com espera crescente (30 s, 2 min), no máximo 3 vezes;
  depois fica "falhou" e vira evento (Central e registro de erros).
- "Rodando" há mais de 15 min sem sinal de vida volta para a fila. Trabalhos
  longos (vídeo) chamam `sinal_de_vida` para não serem devolvidos.
- Só pega tipos que têm executor registrado; os outros esperam na fila.
"""

import logging
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.nucleo.db import sessao as abrir_sessao
from app.nucleo.erros import DadosInvalidos
from app.nucleo.eventos import registrar_evento
from app.nucleo.modelos import Trabalho

log = logging.getLogger("estudio.trabalhador")

MAX_TENTATIVAS = 3
TRAVA = timedelta(minutes=15)
ESPERA_BASE = timedelta(seconds=30)
_SEGREDO = re.compile(r"(?i)(bearer\s+|api[_-]?key[=:]\s*|key=|token[=:]\s*|sk[-_])[\w\-\.]+")


@dataclass(frozen=True)
class Resultado:
    dados: dict[str, Any]
    custo_real: Decimal | None = None


Executor = Callable[[Trabalho], Resultado]


def _agora() -> datetime:
    return datetime.now(UTC)


def limpar_erro(texto: str) -> str:
    """Tira coisas com cara de chave/token antes de guardar e corta o tamanho."""
    return _SEGREDO.sub(lambda m: m.group(1) + "***", texto)[:2000]


def espera(tentativa: int) -> timedelta:
    """30 s depois da 1ª falha, 2 min depois da 2ª."""
    return ESPERA_BASE * (4 ** (tentativa - 1))


# --- operações da fila (cada uma numa transação curta) ------------------------


def pegar_proximo(
    sessao: Session, tipos: list[str], agora: datetime | None = None
) -> Trabalho | None:
    agora = agora or _agora()
    if not tipos:
        return None
    trabalho = sessao.scalar(
        select(Trabalho)
        .where(
            Trabalho.estado == "na_fila",
            Trabalho.proximo_horario <= agora,
            Trabalho.tipo.in_(tipos),
        )
        .order_by(Trabalho.proximo_horario, Trabalho.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if trabalho is None:
        return None
    trabalho.estado = "rodando"
    trabalho.tentativas += 1
    trabalho.travado_ate = agora + TRAVA
    sessao.flush()
    return trabalho


def _exigir_rodando(sessao: Session, trabalho_id: int) -> Trabalho:
    trabalho = sessao.get(Trabalho, trabalho_id, with_for_update=True)
    if trabalho is None or trabalho.estado != "rodando":
        raise DadosInvalidos("o trabalho não está rodando")
    return trabalho


def sinal_de_vida(sessao: Session, trabalho_id: int, agora: datetime | None = None) -> None:
    trabalho = _exigir_rodando(sessao, trabalho_id)
    trabalho.travado_ate = (agora or _agora()) + TRAVA
    sessao.flush()


def concluir(sessao: Session, trabalho_id: int, resultado: Resultado) -> Trabalho:
    trabalho = _exigir_rodando(sessao, trabalho_id)
    trabalho.estado = "concluido"
    trabalho.resultado = resultado.dados
    trabalho.custo_real = resultado.custo_real
    trabalho.travado_ate = None
    trabalho.erro = None
    sessao.flush()
    registrar_evento(
        sessao,
        acao="trabalho_concluido",
        loja_id=trabalho.loja_id,
        detalhes={
            "trabalho_id": trabalho.id,
            "tipo": trabalho.tipo,
            "tentativas": trabalho.tentativas,
        },
        custo=resultado.custo_real,
    )
    from app.pedidos import ao_concluir  # import tardio: pedidos depende da fila

    ao_concluir(sessao, trabalho)  # desconta os créditos de vez (se veio de um pedido)
    return trabalho


def _registrar_falha(sessao: Session, trabalho: Trabalho, erro: str, agora: datetime) -> None:
    trabalho.erro = limpar_erro(erro)
    trabalho.travado_ate = None
    base = {"trabalho_id": trabalho.id, "tipo": trabalho.tipo, "tentativa": trabalho.tentativas}
    if trabalho.tentativas < MAX_TENTATIVAS:
        trabalho.estado = "na_fila"
        trabalho.proximo_horario = agora + espera(trabalho.tentativas)
        acao = "trabalho_retentativa"
    else:
        trabalho.estado = "falhou"
        acao = "trabalho_falhou"  # a Central e o registro de erros leem daqui
    sessao.flush()
    registrar_evento(sessao, acao=acao, loja_id=trabalho.loja_id, detalhes=base)
    if trabalho.estado == "falhou":
        from app.pedidos import ao_falhar_de_vez

        ao_falhar_de_vez(sessao, trabalho)  # devolve os créditos: falha nossa não se cobra


def falhar(sessao: Session, trabalho_id: int, erro: str, agora: datetime | None = None) -> Trabalho:
    trabalho = _exigir_rodando(sessao, trabalho_id)
    _registrar_falha(sessao, trabalho, erro, agora or _agora())
    return trabalho


def devolver_travados(sessao: Session, agora: datetime | None = None) -> int:
    """'Rodando' com a trava vencida (o processo morreu ou travou) volta ou falha."""
    agora = agora or _agora()
    travados = sessao.scalars(
        select(Trabalho)
        .where(Trabalho.estado == "rodando", Trabalho.travado_ate < agora)
        .with_for_update(skip_locked=True)
    ).all()
    for trabalho in travados:
        _registrar_falha(sessao, trabalho, "travado: passou de 15 min sem sinal de vida", agora)
    return len(travados)


# --- o laço -------------------------------------------------------------------


def rodar_uma_vez(executores: Mapping[str, Executor]) -> bool:
    """Um ciclo. Devolve True se executou algum trabalho."""
    with abrir_sessao() as s:
        devolver_travados(s)
    with abrir_sessao() as s:
        trabalho = pegar_proximo(s, list(executores))
        if trabalho is None:
            return False
        s.expunge(trabalho)  # o executor recebe uma cópia solta, sem a transação aberta

    try:
        resultado = executores[trabalho.tipo](trabalho)
    except Exception as erro:  # o executor pode falhar de qualquer jeito
        log.warning("trabalho %s falhou: %s", trabalho.id, type(erro).__name__)
        with abrir_sessao() as s:
            falhar(s, trabalho.id, f"{type(erro).__name__}: {erro}")
        return True
    with abrir_sessao() as s:
        concluir(s, trabalho.id, resultado)
    return True


class Trabalhador:
    """Thread que fica rodando ciclos; dorme um pouco quando a fila está vazia."""

    def __init__(self, executores: Mapping[str, Executor], pausa: float = 2.0):
        self.executores = executores
        self.pausa = pausa
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    def iniciar(self) -> None:
        self._thread = threading.Thread(target=self._laco, name="trabalhador", daemon=True)
        self._thread.start()

    def parar(self, espera_max: float = 10.0) -> None:
        self._parar.set()
        if self._thread:
            self._thread.join(espera_max)

    def vivo(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _laco(self) -> None:
        while not self._parar.is_set():
            try:
                trabalhou = rodar_uma_vez(self.executores)
            except Exception:  # banco fora, por exemplo: espera e tenta de novo
                log.exception("erro no ciclo do trabalhador")
                trabalhou = False
            if not trabalhou:
                self._parar.wait(self.pausa)


def executor_teste(trabalho: Trabalho) -> Resultado:
    """Tipo 'teste': usado na Parada C para ver a fila funcionando no ar, sem gastar."""
    if trabalho.dados.get("falhar"):
        raise RuntimeError("falha de teste pedida")
    return Resultado({"ok": True, "eco": trabalho.dados.get("eco")}, Decimal("0"))


EXECUTORES: dict[str, Executor] = {"teste": executor_teste}
