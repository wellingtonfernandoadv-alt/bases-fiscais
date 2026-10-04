"""
Tabela NCM vigente (Siscomex/Receita Federal), baixada do Portal Único Siscomex.
Guarda todos os niveis (capitulo, posicao, subposicao, item, subitem) e, para cada
codigo, a descricao completa com o caminho (muitos itens se chamam so "Outros").
"""
import json
import urllib.request
from datetime import datetime
from functools import lru_cache

import pandas as pd

from motor.config import DADOS

URL = "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json?perfil=PUBLICO"
ARQ_BASE = DADOS / "base_ncm.csv"
ARQ_META = DADOS / "base_ncm.json"


def _iso(data_br):
    d, m, a = (data_br or "").split("/") if data_br and data_br.count("/") == 2 else ("", "", "")
    return f"{a}-{m}-{d}" if a else ""


def extrai(dados):
    linhas = []
    for n in dados["Nomenclaturas"]:
        cod = n["Codigo"].strip()
        dig = cod.replace(".", "")
        linhas.append({"codigo": cod, "digitos": dig, "nivel": len(dig),
                       "descricao": n["Descricao"].strip().lstrip("- ").strip(),
                       "inicio": _iso(n.get("Data_Inicio")), "fim": _iso(n.get("Data_Fim")),
                       "ato": f"{n.get('Tipo_Ato_Ini', '')} {n.get('Numero_Ato_Ini', '')}/{n.get('Ano_Ato_Ini', '')}".strip()})
    df = pd.DataFrame(linhas)
    desc = dict(zip(df.digitos, df.descricao))
    # caminho: capitulo > posicao > subposicoes > item, para ler "Outros" no contexto
    df["descricao_completa"] = [
        " > ".join(desc[d[:k]] for k in (2, 4, 5, 6, 7, 8) if k <= len(d) and d[:k] in desc)
        for d in df.digitos]
    return df


def atualizar(conteudo=None):
    if conteudo is None:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        conteudo = urllib.request.urlopen(req, timeout=120).read()
    dados = json.loads(conteudo.decode("utf-8-sig") if isinstance(conteudo, bytes) else conteudo)
    df = extrai(dados)
    if (df.nivel == 8).sum() < 5000:
        raise RuntimeError("Tabela NCM com poucos códigos: o formato da fonte mudou?")
    anterior = set(carregar().digitos[carregar().nivel == 8]) if ARQ_BASE.exists() else None
    df.to_csv(ARQ_BASE, index=False, encoding="utf-8-sig", sep=";")
    atuais = set(df.digitos[df.nivel == 8])
    meta = {"atualizado_em": datetime.now().isoformat(timespec="minutes"), "fonte": URL,
            "vigencia": dados.get("Data_Ultima_Atualizacao_NCM", ""), "ato": dados.get("Ato", ""),
            "codigos": len(df), "ncm_8_digitos": len(atuais)}
    if anterior is not None:
        meta["incluidos"] = sorted(atuais - anterior)[:200]
        meta["excluidos"] = sorted(anterior - atuais)[:200]
    ARQ_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    carregar.cache_clear()
    vigentes.cache_clear()
    return meta


@lru_cache(maxsize=1)
def carregar():
    if not ARQ_BASE.exists():
        return pd.DataFrame(columns=["codigo", "digitos", "nivel", "descricao", "inicio", "fim", "ato",
                                     "descricao_completa"])
    return pd.read_csv(ARQ_BASE, sep=";", dtype={"digitos": str, "codigo": str}).fillna("")


@lru_cache(maxsize=1)
def vigentes():
    """NCMs de 8 digitos vigentes (conjunto vazio se a base ainda nao foi baixada)."""
    b = carregar()
    return frozenset(b.digitos[b.nivel == 8])


def descricao(ncm):
    b = carregar()
    r = b[b.digitos == ncm]
    return r.descricao_completa.iloc[0] if len(r) else ""


def meta():
    return json.loads(ARQ_META.read_text(encoding="utf-8")) if ARQ_META.exists() else {}


if __name__ == "__main__":
    print(atualizar())
