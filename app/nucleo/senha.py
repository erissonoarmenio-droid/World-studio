"""Palavra-senha da dona (tarefa 8). Decisões de Eri de 25/10, 11h47 e 11h50.

- Só a dona tem. É pedida SÓ para comprar créditos, mudar ou cancelar o plano
  e ligar o modo automático. O dia a dia é só "sim"/"não", sem senha.
- Guardada só como hash Argon2id. Digitada certa, vale 30 minutos.
- 5 erros seguidos: bloqueio de 15 minutos + evento (aviso à dona e à Central).
- Esqueceu (piloto): o Eri confirma quem é e libera a troca pela Central; a
  dona cria uma palavra nova na conversa.
- Comparação sem diferença de maiúsculas e espaços repetidos: o teclado do
  celular costuma pôr a primeira letra em maiúscula sozinho.
- Nada da palavra (nem o tamanho) vai para evento ou log.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.orm import Session

from app.nucleo.erros import (
    Conflito,
    DadosInvalidos,
    NaoEncontrado,
    PalavraBloqueada,
    PalavraNecessaria,
    SemPermissao,
)
from app.nucleo.eventos import Autor, registrar_evento
from app.nucleo.modelos import PalavraSenha, Pessoa
from app.nucleo.pessoas import obter_pessoa

JANELA = timedelta(minutes=30)
BLOQUEIO = timedelta(minutes=15)
MAX_ERROS = 5
PRAZO_TROCA = timedelta(hours=24)
_hasher = PasswordHasher()  # Argon2id, parâmetros recomendados pela RFC 9106


def _agora() -> datetime:
    return datetime.now(UTC)


def _normalizar(palavra: str) -> str:
    return " ".join(palavra.split()).casefold()


def _obter_dona(sessao: Session, pessoa_id: int) -> Pessoa:
    pessoa = obter_pessoa(sessao, pessoa_id)
    if pessoa.papel != "dona":
        raise SemPermissao("só a dona da loja tem palavra-senha")
    return pessoa


def _obter_registro(sessao: Session, pessoa_id: int) -> PalavraSenha:
    registro = sessao.get(PalavraSenha, pessoa_id)
    if registro is None:
        raise NaoEncontrado("a dona ainda não criou a palavra-senha")
    return registro


def criar_palavra(
    sessao: Session,
    pessoa_id: int,
    palavra: str,
    autor: Autor,
    dica: str | None = None,
    agora: datetime | None = None,
) -> PalavraSenha:
    """Cria a primeira palavra, ou troca quando o Eri liberou a troca."""
    agora = agora or _agora()
    pessoa = _obter_dona(sessao, pessoa_id)
    if autor.tipo != "pessoa" or autor.pessoa_id != pessoa.id:
        raise SemPermissao("a palavra-senha só pode ser criada pela própria dona")
    normal = _normalizar(palavra)
    if not 4 <= len(normal) <= 64:
        raise DadosInvalidos("a palavra-senha deve ter de 4 a 64 letras")
    if dica is not None:
        dica = dica.strip() or None
    if dica is not None and (len(dica) > 100 or normal in _normalizar(dica)):
        raise DadosInvalidos("a dica não pode conter a palavra-senha nem passar de 100 letras")

    registro = sessao.get(PalavraSenha, pessoa.id)
    troca = registro is not None
    if troca and not (registro.troca_liberada_ate and registro.troca_liberada_ate > agora):
        raise Conflito("a palavra-senha já existe; para trocar, o Eri precisa liberar")

    registro = registro or PalavraSenha(pessoa_id=pessoa.id)
    registro.hash = _hasher.hash(normal)
    registro.dica = dica
    registro.tentativas_erradas = 0
    registro.bloqueada_ate = registro.valida_ate = registro.troca_liberada_ate = None
    sessao.add(registro)
    sessao.flush()
    registrar_evento(
        sessao,
        acao="palavra_trocada" if troca else "palavra_criada",
        autor=autor,
        loja_id=pessoa.loja_id,
        detalhes={"pessoa_id": pessoa.id, "com_dica": dica is not None},
    )
    return registro


def conferir_palavra(
    sessao: Session, pessoa_id: int, palavra: str, agora: datetime | None = None
) -> bool:
    """True abre a janela de 30 min. False conta o erro (quem chama deve gravar).

    Bloqueada: levanta PalavraBloqueada sem nem conferir.
    """
    agora = agora or _agora()
    pessoa = _obter_dona(sessao, pessoa_id)
    registro = _obter_registro(sessao, pessoa.id)
    if registro.bloqueada_ate and registro.bloqueada_ate > agora:
        minutos = int((registro.bloqueada_ate - agora).total_seconds() // 60) + 1
        raise PalavraBloqueada(f"palavra-senha bloqueada; tente de novo em {minutos} min")

    autor = Autor("pessoa", pessoa.id)
    try:
        certa = _hasher.verify(registro.hash, _normalizar(palavra))
    except (VerificationError, InvalidHashError):
        certa = False

    if certa:
        if _hasher.check_needs_rehash(registro.hash):
            registro.hash = _hasher.hash(_normalizar(palavra))
        registro.tentativas_erradas = 0
        registro.bloqueada_ate = None
        registro.valida_ate = agora + JANELA
        sessao.flush()
        registrar_evento(
            sessao,
            acao="palavra_conferida",
            autor=autor,
            loja_id=pessoa.loja_id,
            detalhes={"pessoa_id": pessoa.id},
        )
        return True

    registro.tentativas_erradas += 1
    registro.valida_ate = None
    detalhes = {"pessoa_id": pessoa.id, "tentativa": registro.tentativas_erradas}
    if registro.tentativas_erradas >= MAX_ERROS:
        registro.bloqueada_ate = agora + BLOQUEIO
        registro.tentativas_erradas = 0
        acao = "palavra_bloqueada"  # a Central e a dona são avisadas a partir deste evento
    else:
        acao = "palavra_errada"
    sessao.flush()
    registrar_evento(sessao, acao=acao, autor=autor, loja_id=pessoa.loja_id, detalhes=detalhes)
    return False


def janela_aberta(sessao: Session, pessoa_id: int, agora: datetime | None = None) -> bool:
    registro = sessao.get(PalavraSenha, pessoa_id)
    agora = agora or _agora()
    return bool(registro and registro.valida_ate and registro.valida_ate > agora)


def exigir_palavra(sessao: Session, pessoa_id: int, agora: datetime | None = None) -> None:
    """Usar antes de comprar créditos, mudar/cancelar plano ou ligar o modo automático."""
    _obter_dona(sessao, pessoa_id)
    if not janela_aberta(sessao, pessoa_id, agora):
        raise PalavraNecessaria("essa ação precisa da palavra-senha da dona")


def fechar_janela(sessao: Session, pessoa_id: int) -> None:
    """Fecha a janela antes dos 30 min (ex.: a dona pede "pode trancar")."""
    registro = sessao.get(PalavraSenha, pessoa_id)
    if registro and registro.valida_ate:
        registro.valida_ate = None
        sessao.flush()


def liberar_troca(
    sessao: Session, pessoa_id: int, autor: Autor, agora: datetime | None = None
) -> PalavraSenha:
    """Só o Eri, depois de confirmar quem é a dona. Também tira o bloqueio."""
    if autor.tipo != "eri":
        raise SemPermissao("só o Eri libera a troca da palavra-senha")
    agora = agora or _agora()
    pessoa = _obter_dona(sessao, pessoa_id)
    registro = _obter_registro(sessao, pessoa.id)
    registro.troca_liberada_ate = agora + PRAZO_TROCA
    registro.bloqueada_ate = None
    registro.tentativas_erradas = 0
    registro.valida_ate = None
    sessao.flush()
    registrar_evento(
        sessao,
        acao="troca_palavra_liberada",
        autor=autor,
        loja_id=pessoa.loja_id,
        detalhes={"pessoa_id": pessoa.id},
    )
    return registro


def apagar_mensagem_da_palavra(
    sessao: Session,
    pessoa_id: int,
    apagar: Callable[[], None],
) -> bool:
    """O módulo `conversa` passa a função que apaga a mensagem no Telegram.

    Se o Telegram recusar (mensagem antiga, sem permissão), registra o evento
    para a Central avisar a dona a apagar à mão. Nunca recebe a palavra.
    """
    pessoa = obter_pessoa(sessao, pessoa_id)
    try:
        apagar()
    except Exception:
        registrar_evento(
            sessao,
            acao="mensagem_palavra_nao_apagada",
            loja_id=pessoa.loja_id,
            detalhes={"pessoa_id": pessoa.id},
        )
        return False
    return True
