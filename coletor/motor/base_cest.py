"""
Tabela nacional do CEST: Anexos II a XXVI do Convenio ICMS 142/2018 (CONFAZ).

A pagina do CONFAZ intercala o texto vigente com as redacoes anteriores. Cada
redacao antiga vem depois de uma linha de nota ("Redacao anterior...", "Redacao
original..."); essas linhas sao descartadas e so a redacao vigente e gravada.

Clausula vigesima, I: o documento fiscal deve conter "o CEST de cada bem e
mercadoria, ainda que a operacao nao esteja sujeita ao regime de substituicao
tributaria".
"""
import json
import re
import urllib.request
from datetime import datetime
from functools import lru_cache

import pandas as pd
from bs4 import BeautifulSoup

from motor.base_st import limpa
from motor.config import DADOS

URL = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18"
ARQ_BASE = DADOS / "base_cest.csv"
ARQ_META = DADOS / "base_cest.json"
ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII",
           "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII", "XXIV",
           "XXV", "XXVI"]
ANEXOS_CEST = set(ROMANOS[1:])  # II a XXVI


def _tipo_nota(txt):
    t = txt.lower()
    if "anterior" in t or "original" in t:
        return "historico"
    if "revogad" in t and "nova reda" not in t:
        return "revogado"
    return "vigente"


def extrai_html(html):
    soup = BeautifulSoup(html, "lxml")
    registros = []
    for tab in soup.find_all("table"):
        cab = tab.find_previous(string=re.compile(r"ANEXO\s+[IVX]+"))
        m = re.search(r"ANEXO\s+([IVX]+)\b", limpa(cab or ""))
        if not m or m.group(1) not in ANEXOS_CEST:
            continue
        anexo = m.group(1)
        # o titulo do segmento e o texto logo apos "ANEXO X"
        seg = limpa(cab.find_parent().get_text(" ") if cab.find_parent() else cab)
        seg = re.sub(r"^.*?ANEXO\s+" + anexo + r"\b", "", seg).strip()
        seg = re.split(r"\s+ITEM\b|\(", seg)[0].strip()
        if not seg:
            prox = cab.find_next(string=lambda s: s and limpa(s) and "ANEXO" not in s)
            seg = limpa(prox or "")
        modo, item_do_modo = "vigente", None
        for tr in tab.find_all("tr"):
            cel = [limpa(c.get_text(" ")) for c in tr.find_all(["td", "th"])]
            if not cel or cel[0].upper() == "ITEM":
                continue
            if len(cel) < 4:  # linha de nota sobre a redacao que vem a seguir
                modo, item_do_modo = _tipo_nota(" ".join(cel)), None
                continue
            item, cest, ncm_txt, desc = cel[:4]
            if not re.fullmatch(r"\d{2}\.\d{3}\.\d{2}", cest):
                continue
            # a nota vale para o item que vem logo depois dela
            if item_do_modo is None:
                item_do_modo = item
            elif item != item_do_modo:
                modo, item_do_modo = "vigente", item
            if modo != "vigente":
                continue
            ncms = re.findall(r"\d{2,4}(?:\.\d{1,2}){0,2}", ncm_txt)
            for ncm in [x for x in ncms if len(x.replace(".", "")) >= 4]:
                registros.append({"anexo": anexo, "segmento": seg[:80].capitalize(),
                                  "item": item, "cest": cest, "ncm_norma": ncm,
                                  "ncm_prefixo": ncm.replace(".", ""), "descricao_norma": desc})
    df = pd.DataFrame(registros)
    # a mesma redacao pode aparecer repetida; fica uma linha por CEST x NCM
    return df.drop_duplicates(["cest", "ncm_prefixo"]).reset_index(drop=True)


def atualizar(html=None):
    if html is None:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "ignore")
    df = extrai_html(html)
    if df.cest.nunique() < 500:
        raise RuntimeError(f"Extração suspeita: só {df.cest.nunique()} CESTs. A página mudou?")
    df.to_csv(ARQ_BASE, index=False, encoding="utf-8-sig", sep=";")
    meta = {"atualizado_em": datetime.now().isoformat(timespec="minutes"), "fonte": URL,
            "registros": len(df), "cests": int(df.cest.nunique())}
    ARQ_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    carregar.cache_clear()
    return meta


@lru_cache(maxsize=1)
def carregar():
    if not ARQ_BASE.exists():
        return pd.DataFrame(columns=["anexo", "segmento", "item", "cest", "ncm_norma",
                                     "ncm_prefixo", "descricao_norma"])
    return pd.read_csv(ARQ_BASE, sep=";", dtype=str).fillna("")


def meta():
    return json.loads(ARQ_META.read_text(encoding="utf-8")) if ARQ_META.exists() else {}


def itens_do_ncm(ncm, incluir_porta_a_porta=False):
    base = carregar()
    if not ncm or base.empty:
        return base.iloc[0:0]
    hits = base[[ncm.startswith(p) for p in base.ncm_prefixo]]
    if not incluir_porta_a_porta:  # Anexo XXVI so vale para venda porta a porta
        hits = hits[hits.anexo != "XXVI"]
    return hits


if __name__ == "__main__":
    print(atualizar())
