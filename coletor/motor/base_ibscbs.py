"""
IBS/CBS: tabela oficial de classificacao tributaria (CST e cClassTrib) do Portal da
Conformidade Facil, com os NCM/NBS de cada codigo (anexos da LC 214/2025).

A pagina publica https://dfe-portal.svrs.rs.gov.br/Cff/ClassificacaoTributaria traz a
tabela inteira embutida (variavel JavaScript `dadosOriginais`). Este modulo baixa a
pagina, guarda o JSON em dados/fontes e gera duas bases:

  base_ibscbs.csv        um registro por cClassTrib (CST, reducoes, documentos, anexo, link da lei)
  base_ibscbs_itens.csv  um registro por NCM/NBS ligado a um cClassTrib, com PERMITIDO/VEDADO,
                         condicao e excecao em texto e o item do anexo da lei
"""
import gzip
import json
import urllib.request
from datetime import datetime
from functools import lru_cache

import pandas as pd

from motor.config import DADOS

URL = "https://dfe-portal.svrs.rs.gov.br/Cff/ClassificacaoTributaria"
ARQ_BASE = DADOS / "base_ibscbs.csv"
ARQ_META = DADOS / "base_ibscbs.json"
ARQ_ITENS = DADOS / "base_ibscbs_itens.csv"
ARQ_FONTE = DADOS / "fontes" / "cff_classtrib.json.gz"

COLUNAS = ["cst", "cst_nome", "cclasstrib", "descricao", "nome_reduzido", "red_ibs", "red_cbs",
           "tipo_aliquota", "nfe", "nfce", "nfse", "anexo", "url", "inicio", "fim", "publicacao"]
COLUNAS_ITENS = ["cclasstrib", "tipo", "codigo", "permissao", "condicao", "excecao", "item_anexo",
                 "anexo_nome", "nro_anexo", "observacao", "inicio", "fim"]


def _data(v):
    return (v or "")[:10]


def _texto(v):
    return " ".join(str(v).split()) if v else ""


def ler_pagina(html):
    """Extrai a lista `dadosOriginais` (CSTs com as classificacoes e os anexos) do HTML."""
    marca = "var dadosOriginais = "
    i = html.find(marca)
    if i < 0:
        raise RuntimeError("Página sem a tabela (dadosOriginais): o layout do portal mudou?")
    dados, _ = json.JSONDecoder().raw_decode(html[i + len(marca):])
    return dados


def extrai(dados):
    linhas, itens = [], []
    for cst in dados:
        for ct in cst.get("ClassificacoesTributarias") or []:
            linhas.append({
                "cst": cst["Cst"], "cst_nome": _texto(cst.get("NomeCst")),
                "cclasstrib": ct["CodClassTrib"], "descricao": _texto(ct.get("NomeClassTrib")),
                "nome_reduzido": _texto(ct.get("NomeReduzido")),
                "red_ibs": f'{float(ct.get("PercRedIbs") or 0):g}', "red_cbs": f'{float(ct.get("PercRedCbs") or 0):g}',
                "tipo_aliquota": ct.get("TipoAliq") or "",
                "nfe": "S" if ct.get("IndNfe") else "N", "nfce": "S" if ct.get("IndNfce") else "N",
                "nfse": "S" if ct.get("IndNfse") else "N",
                "anexo": ct.get("NroAnexo") or "", "url": ct.get("TexUrlLegislacao") or "",
                "inicio": _data(ct.get("DthIniVig")), "fim": _data(ct.get("DthFimVig")),
                "publicacao": _data(ct.get("DthPublicacao")),
            })
            for a in ct.get("Anexos") or []:
                itens.append({
                    "cclasstrib": ct["CodClassTrib"], "tipo": a.get("TipoCodigo") or "",
                    "codigo": (a.get("CodNcmNbs") or "").strip(), "permissao": a.get("TipoPermissao") or "",
                    "condicao": _texto(a.get("DescCondicao")), "excecao": _texto(a.get("DescExcecao")),
                    "item_anexo": _texto(a.get("DescItemAnexo")), "anexo_nome": _texto(a.get("DescAnexo")),
                    "nro_anexo": a.get("NroAnexo") or "", "observacao": _texto(a.get("Observacao")),
                    "inicio": _data(a.get("DthIniVig")), "fim": _data(a.get("DthFimVig")),
                })
    df = pd.DataFrame(linhas, columns=COLUNAS).sort_values("cclasstrib")
    di = pd.DataFrame(itens, columns=COLUNAS_ITENS).sort_values(["cclasstrib", "tipo", "codigo", "item_anexo"])
    return df, di


def atualizar(conteudo=None):
    if conteudo is None:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        conteudo = urllib.request.urlopen(req, timeout=180).read()
    html = conteudo.decode("utf-8", errors="replace") if isinstance(conteudo, bytes) else conteudo
    dados = ler_pagina(html)
    df, di = extrai(dados)
    if len(df) < 150 or (di.tipo == "NCM").sum() < 3000:
        raise RuntimeError(f"Tabela IBS/CBS incompleta ({len(df)} cClassTrib, {(di.tipo == 'NCM').sum()} NCM)")
    ARQ_FONTE.write_bytes(gzip.compress(json.dumps(dados, ensure_ascii=False).encode("utf-8"), mtime=0))
    anterior = set(carregar().cclasstrib) if ARQ_BASE.exists() else None
    df.to_csv(ARQ_BASE, index=False, encoding="utf-8-sig", sep=";")
    di.to_csv(ARQ_ITENS, index=False, encoding="utf-8-sig", sep=";")
    meta = {"atualizado_em": datetime.now().isoformat(timespec="minutes"), "fonte": URL,
            "cclasstrib": len(df), "ncm": int((di.tipo == "NCM").sum()), "nbs": int((di.tipo == "NBS").sum()),
            "publicacao_mais_recente": max(df.publicacao)}
    if anterior is not None:
        meta["incluidos"] = sorted(set(df.cclasstrib) - anterior)
        meta["excluidos"] = sorted(anterior - set(df.cclasstrib))
    ARQ_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    carregar.cache_clear()
    carregar_itens.cache_clear()
    return meta


@lru_cache(maxsize=1)
def carregar():
    if not ARQ_BASE.exists():
        return pd.DataFrame(columns=COLUNAS)
    return pd.read_csv(ARQ_BASE, sep=";", dtype=str).fillna("")


@lru_cache(maxsize=1)
def carregar_itens():
    if not ARQ_ITENS.exists():
        return pd.DataFrame(columns=COLUNAS_ITENS)
    return pd.read_csv(ARQ_ITENS, sep=";", dtype=str).fillna("")


def meta():
    return json.loads(ARQ_META.read_text(encoding="utf-8")) if ARQ_META.exists() else {}
