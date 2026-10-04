"""
Base normativa do ICMS-ST de SP: extrai os anexos da Portaria CAT 68/2019 do site
da Sefaz-SP e grava um registro por NCM de cada item, com a situacao
(VIGENTE/REVOGADO), a norma revogadora e a data a partir da qual deixou de ser ST.
"""
import json
import re
import urllib.request
from datetime import datetime
from functools import lru_cache

import pandas as pd
from bs4 import BeautifulSoup

from motor.config import DADOS

URL = "https://legislacao.fazenda.sp.gov.br/Paginas/Portaria-CAT-68-de-2019.aspx"
ARQ_BASE = DADOS / "base_cat68.csv"
ARQ_META = DADOS / "base_cat68.json"
MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4,
         "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
         "outubro": 10, "novembro": 11, "dezembro": 12}


def limpa(txt):
    return re.sub(r"\s+", " ", txt.replace("​", " ").replace("\xa0", " ")).strip()


def extrai_revogacao(txt):
    """Retorna (norma, data_efeito) se o texto indicar revogacao; senao (None, None).
    A data e a do 1o dia sem ST. Sem vigencia explicita, usa a data do DOE."""
    if not re.search(r"r\s?evogad", txt, re.I):
        return None, None
    norma = re.search(r"Portaria\s+(?:SRE|CAT)\s*-?\s*\d+/\d+", txt, re.I)
    norma = re.sub(r"\s*-\s*", "-", norma.group(0)) if norma else "revogado"
    m = re.search(r"1[ºo°]?\s+de\s+([a-zç]+)\s+de\s+(\d{4})", txt, re.I)
    if m and m.group(1).lower() in MESES:
        return norma, f"{m.group(2)}-{MESES[m.group(1).lower()]:02d}-01"
    m = re.search(r"DOE\s+(\d{2})[-/](\d{2})\s*[-/]\s*(\d{4})", txt)
    if m:
        return norma, f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return norma, None


def extrai_html(html):
    soup = BeautifulSoup(html, "lxml")
    tabelas = [t for t in soup.find_all("table")
               if "CEST" in t.get_text() and "NCM" in t.get_text()]
    registros = []
    for tab in tabelas:
        # cabecalho do anexo: paragrafos entre o titulo "ANEXO X" e a tabela
        partes, n = [], tab.find_previous_sibling()
        while n is not None and len(partes) < 6:
            t = limpa(n.get_text(" "))
            partes.insert(0, t)
            if re.search(r"ANEXO\s+[IVX]+", t):
                break
            n = n.find_previous_sibling()
        cab = limpa(" ".join(partes))
        if not cab:
            no = tab.find_previous(string=re.compile(r"ANEXO\s+[IVX]+"))
            cab = limpa(no) if no else ""
        m = re.search(r"ANEXO\s+([IVX]+)\b", cab)
        anexo = m.group(1) if m else "?"
        segmento = re.sub(r"\(.*?\)", "", cab.split("ANEXO " + anexo, 1)[-1]).strip(" -")
        segmento = re.split(r"\s+NOTA\b|\s+ITEM\b", segmento)[0]
        segmento = re.sub(r"\s+", " ", segmento)[:80]
        norma_anexo, data_anexo = extrai_revogacao(cab.split("ITEM")[0][:400])

        for tr in tab.find_all("tr")[1:]:
            cel = [limpa(c.get_text(" ")) for c in tr.find_all(["td", "th"])]
            if len(cel) < 4:
                continue
            item_txt, cest, ncm_txt, desc = cel[0], cel[1], cel[2], cel[3]
            item = re.match(r"\d+(\.\d+)?", item_txt)
            item = item.group(0) if item else item_txt[:10]
            norma_item, data_item = extrai_revogacao(item_txt + " " + desc[:200])
            norma = norma_anexo or norma_item
            data = data_anexo or data_item
            ncms = re.findall(r"\d{2,4}(?:\.\d{1,2}){0,2}", ncm_txt)
            ncms = [x for x in ncms if len(x.replace(".", "")) >= 4] or [ncm_txt]
            for ncm in ncms:
                registros.append({
                    "anexo": anexo, "segmento": segmento.capitalize(), "item": item,
                    "cest": cest, "ncm_norma": ncm, "ncm_prefixo": ncm.replace(".", ""),
                    "descricao_norma": desc,
                    "situacao": "REVOGADO" if norma else "VIGENTE",
                    "revogado_por": norma or "", "sem_st_desde": data or "",
                })
    return pd.DataFrame(registros)


def atualizar(html=None):
    """Baixa a portaria (ou usa o HTML informado), regrava a base e devolve o resumo."""
    if html is None:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "ignore")
    df = extrai_html(html)
    if len(df) < 500:
        raise RuntimeError(f"Extração suspeita: só {len(df)} registros. A página mudou?")
    anterior = carregar() if ARQ_BASE.exists() else None
    df.to_csv(ARQ_BASE, index=False, encoding="utf-8-sig", sep=";")
    meta = {"atualizado_em": datetime.now().isoformat(timespec="minutes"),
            "fonte": URL, "registros": len(df),
            "itens": int(df.drop_duplicates(["anexo", "item"]).shape[0])}
    if anterior is not None:
        chave = ["anexo", "item", "ncm_prefixo", "situacao", "sem_st_desde"]
        a = set(map(tuple, anterior[chave].values))
        b = set(map(tuple, df[chave].values))
        meta["alteracoes"] = len(a ^ b)
    ARQ_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    carregar.cache_clear()
    return meta


@lru_cache(maxsize=1)
def carregar():
    return pd.read_csv(ARQ_BASE, sep=";", dtype=str).fillna("")


def meta():
    if ARQ_META.exists():
        return json.loads(ARQ_META.read_text(encoding="utf-8"))
    return {}


def itens_do_ncm(ncm):
    """Registros da base cujo NCM (prefixo) alcanca o NCM de 8 digitos informado."""
    base = carregar()
    return base[[ncm.startswith(p) for p in base.ncm_prefixo]] if ncm else base.iloc[0:0]


def vigente_em(linhas, data_ref):
    """Mascara: o item ainda estava em ST na data de referencia (AAAA-MM-DD)."""
    return (linhas.situacao == "VIGENTE") | (linhas.sem_st_desde > data_ref)


if __name__ == "__main__":
    print(atualizar())
