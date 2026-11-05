"""Tabela de preços da Desfila: planos, pacotes extras e quanto cada coisa custa em créditos.

São DUAS tabelas separadas de propósito (decisão de 05/11):
1. PRECO_CREDITOS: o que a lojista paga, em créditos. Não muda quando trocamos de fornecedor.
2. CUSTO_FORNECEDOR: quanto NÓS pagamos a cada fornecedor (estimado, em US$). Se a Tein for
   trocada por outra plataforma, só esta tabela muda; a lojista não percebe.

Fontes: `aios/operations/financeiro-estudio.md` §0 (preços de 01/11, custos medidos com o que a
Tein cobrou de verdade) e decisões de Eri de 05/11 (sem teste grátis; 1ª influencer no plano com
3 ajustes; até 3 influencers de corpos diferentes, a 2ª e a 3ª por 5 créditos).
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Plano:
    nome: str
    preco_centavos: int  # em reais × 100
    creditos_mes: int
    social_media: bool  # o plano Social Media libera artes e as funções de social media


@dataclass(frozen=True)
class Pacote:
    nome: str
    preco_centavos: int
    creditos: int


PLANOS: dict[str, Plano] = {
    "estudio": Plano("Estúdio", 19700, 75, social_media=False),
    "social_media": Plano("Social Media", 59700, 180, social_media=True),
}

PACOTES_EXTRAS: dict[str, Pacote] = {
    "extra_30": Pacote("30 créditos", 5900, 30),
    "extra_100": Pacote("100 créditos", 19900, 100),
}

# Validade (decisão de 25/10, mantida em 01/11): créditos do plano vencem no fim do ciclo
# (na renovação); extras valem 90 dias. Ajuste a mais feito pelo Eri: 90 dias.
DIAS_VALIDADE_EXTRA = 90
DIAS_VALIDADE_AJUSTE = 90
DIAS_VALIDADE_ESTORNO = 30  # estorno que volta para um lote já vencido
DIAS_AVISO_VENCIMENTO = 3
DIAS_GUARDAR_DADOS_DEPOIS_DE_CANCELAR = 60

AJUSTES_ROSTO_SEM_CUSTO = 3  # por influencer, na criação
MAX_INFLUENCERS_POR_LOJA = 3

# Preço em créditos de cada item (o que a lojista paga).
PRECO_CREDITOS: dict[str, int] = {
    "foto": 2,  # foto da influencer com a peça (2 opções)
    "foto_outro_corpo": 2,  # a mesma peça vestida em outra influencer da loja (R2)
    "foto_produto": 2,  # foto de produto sem influencer (2 opções)
    "arte": 1,  # arte de post/story com preço (só no Social Media)
    "video_480": 15,  # vídeo UGC 480p até 16 s, 1 ângulo
    "video_2_angulos": 25,  # os 2 ângulos de venda
    "video_720": 30,  # só se a lojista pedir
    "voz_exclusiva": 20,
    "influencer_principal": 0,  # a 1ª influencer vem no plano
    "influencer_extra": 5,  # 2ª e 3ª (outros corpos, rostos diferentes)
    "ajuste_rosto": 2,  # a partir do 4º ajuste de cada influencer
}

ITENS_SO_SOCIAL_MEDIA = frozenset({"arte"})


@dataclass(frozen=True)
class CustoFornecedor:
    fornecedor: str
    usd: Decimal


# Nosso custo estimado por item (US$), medido em 30/10–01/11 (financeiro §2).
CUSTO_FORNECEDOR: dict[str, CustoFornecedor] = {
    "foto": CustoFornecedor("google", Decimal("0.05")),
    "foto_outro_corpo": CustoFornecedor("google", Decimal("0.05")),
    "foto_produto": CustoFornecedor("google", Decimal("0.05")),
    "arte": CustoFornecedor("google", Decimal("0.03")),
    "video_480": CustoFornecedor("tein", Decimal("2.15")),
    "video_2_angulos": CustoFornecedor("tein", Decimal("4.25")),
    "video_720": CustoFornecedor("tein", Decimal("4.60")),
    "voz_exclusiva": CustoFornecedor("voz", Decimal("3.00")),
    "influencer_principal": CustoFornecedor("google", Decimal("0.40")),
    "influencer_extra": CustoFornecedor("google", Decimal("0.40")),
    "ajuste_rosto": CustoFornecedor("google", Decimal("0.05")),
}

# Teto de gasto por dia e por fornecedor (US$). Passou: para tudo daquele fornecedor e avisa
# o Eri. Pode ser trocado sem mexer no código pela variável TETOS_DIARIOS_USD (ex.:
# '{"tein": 25}').
TETO_DIARIO_USD: dict[str, Decimal] = {
    "tein": Decimal("15"),
    "google": Decimal("3"),
    "voz": Decimal("10"),
}

# Custo real acima disso × o estimado vira alerta para o Eri.
LIMITE_ALERTA_CUSTO = Decimal("1.3")

assert set(PRECO_CREDITOS) == set(CUSTO_FORNECEDOR), "todo item precisa de preço e custo"
