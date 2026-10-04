"""
PIS/COFINS de incidencia monofasica (concentrada no fabricante/importador).

Fontes:
  - Tabela 4.3.10 do SPED (RFB): combustiveis, farmacos, perfumaria, veiculos e
    maquinas, pneus e bebidas frias. Arquivo .doc convertido para .docx.
  - Lei 10.485/2002, Anexos I e II (autopecas), texto consolidado do Planalto,
    descartando o que esta riscado (revogado).

Cada registro diz se a regra e direta ou condicional (depende do destino/uso do
produto ou de "Ex" tarifario) e, nesse caso, o motivo.
"""
import json
import re
import shutil
import subprocess
import urllib.request
import zipfile
from datetime import datetime
from functools import lru_cache
from xml.etree import ElementTree as ET

import pandas as pd
from bs4 import BeautifulSoup

from motor.config import DADOS

FONTES = DADOS / "fontes"
URL_SPED = "http://sped.rfb.gov.br/arquivo/download/1638"
URL_LEI = "https://www.planalto.gov.br/ccivil_03/leis/2002/l10485.htm"
ARQ_BASE = DADOS / "base_monofasico.csv"
ARQ_META = DADOS / "base_monofasico.json"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
COD = re.compile(r"\b\d{2}\.?\d{2}(?:\.\d{1,2}){0,2}(?:\s*Ex\s*\d+(?:\s*e\s*\d+)?)?")


def _registro(ncm_txt, grupo, descricao, fonte, condicao=""):
    ex = re.search(r"Ex\s*([\d\se]+)", ncm_txt)
    ncm = re.sub(r"\s*Ex.*", "", ncm_txt).strip()
    if ex:
        condicao = (condicao + "; " if condicao else "") + f"Só o Ex {ex.group(1).strip()} da TIPI"
    return {"ncm_norma": ncm_txt.strip(), "ncm_prefixo": re.sub(r"\D", "", ncm), "grupo": grupo,
            "descricao": descricao, "fonte": fonte, "condicao": condicao}


def _linhas_docx(caminho):
    raiz = ET.fromstring(zipfile.ZipFile(caminho).read("word/document.xml"))
    for tr in raiz.iter(W + "tr"):
        celulas = []
        for tc in tr.findall(W + "tc"):
            pars = ["".join(t.text or "" for t in p.iter(W + "t")).strip() for p in tc.findall(W + "p")]
            celulas.append([p for p in pars if p])
        yield celulas


def extrai_sped(caminho_docx):
    """Linhas vigentes (sem termino) da Tabela 4.3.10 que listam NCMs."""
    regs, excecoes, grupo, bebidas_vigentes = [], [], "", False
    for cel in _linhas_docx(caminho_docx):
        if len(cel) < 2 or not cel[0]:
            continue
        codigo, desc = cel[0][0], " ".join(cel[1])
        if re.fullmatch(r"\d00", codigo):  # cabecalho de grupo (pode ter celulas mescladas)
            grupo = desc.split("–")[0].strip().capitalize()
            # bebidas frias: a linha do produto traz a 1a vigencia; as aliquotas
            # atuais estao nas linhas de continuacao, entao o termino nao vale aqui
            bebidas_vigentes = codigo == "400" and "partir" in desc and "2015" in desc
            continue
        if len(cel) < 3:
            continue
        termino = " ".join(cel[6]) if len(cel) > 6 else ""
        ncm_txt = " ".join(cel[2])
        if bebidas_vigentes:
            termino = ""
        if termino or not ncm_txt or ncm_txt == "-" or "10.485" in ncm_txt:
            continue
        condicao = ""
        if "Capítulo 84" in desc or "autopropulsad" in desc.lower():
            condicao = "Capítulo 84: só máquinas autopropulsadas (não as partes)"
        for par in cel[2]:
            for exc in re.findall(r"\(exceto[^)]*\)", par):
                excecoes += [re.sub(r"\D", "", c) for c in COD.findall(exc) if "Ex" not in c]
            par = re.sub(r"\(exceto[^)]*\)", "", par)
            if re.search(r",?\s*exceto", par):  # exceto Ex de um codigo: vira condicao
                par, resto = re.split(r",?\s*exceto", par, maxsplit=1)
                condicao = "Exceto " + resto.strip()
            for c in COD.findall(par):
                regs.append(_registro(c, grupo, f"{codigo} - {desc[:120]}", "SPED Tabela 4.3.10",
                                      condicao if re.sub(r"\D", "", c).startswith("84") else ""))
    return regs, excecoes


def extrai_lei(html):
    soup = BeautifulSoup(html, "lxml")
    for riscado in soup.find_all(["strike", "s", "del"]):
        riscado.decompose()
    txt = re.sub(r"\s+", " ", soup.get_text(" "))
    i, j = txt.find("ANEXO I "), txt.find("ANEXO II")
    fim = txt.find("*", j)
    anexo1 = re.sub(r"\(Reda[^)]*\)|\(Vide[^)]*\)", "", txt[i:j])
    anexo2 = txt[j:fim if fim > 0 else j + 8000]
    regs = [_registro(c, "Autopeças", "Lei 10.485/2002, Anexo I", "Lei 10.485/2002 - Anexo I")
            for c in COD.findall(anexo1)]
    for item in re.split(r"\s(?=\d{1,2}\.\s[A-ZÁÉÍÓÚ])", anexo2)[1:]:
        m = re.match(r"(\d+)\.\s(.*)", item.strip())
        if not m:
            continue
        num, texto = m.groups()
        # o primeiro codigo citado e o do produto; os demais sao os veiculos de destino
        cod = COD.search(re.sub(r"posi[çc][ãa]o|c[óo]digo", "", texto))
        if cod:
            regs.append(_registro(cod.group(0), "Autopeças",
                                  f"Lei 10.485/2002, Anexo II, item {num}: {texto[:160].rstrip(';')}",
                                  "Lei 10.485/2002 - Anexo II",
                                  "Só quando próprio para os veículos/máquinas indicados no item"))
    return regs


def _baixar_tabela_sped(docx):
    """Baixa a Tabela 4.3.10 (.doc do Word 97) e converte para .docx: pelo LibreOffice
    quando houver (GitHub Actions), senao pelo Word instalado (Windows)."""
    doc = docx.with_suffix(".doc")
    req = urllib.request.Request(URL_SPED, headers={"User-Agent": "Mozilla/5.0"})
    doc.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    if shutil.which("soffice"):  # Linux do GitHub Actions: LibreOffice
        subprocess.run(["soffice", "--headless", "--convert-to", "docx", "--outdir", str(doc.parent), str(doc)],
                       check=True, timeout=300, capture_output=True)
        return
    script = (f'$w = New-Object -ComObject Word.Application; $w.Visible = $false; '
              f'$d = $w.Documents.Open("{doc}", $false, $true); $d.SaveAs2("{docx}", 16); '
              f'$d.Close($false); $w.Quit()')
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, timeout=180)


def atualizar():
    FONTES.mkdir(exist_ok=True)
    docx = FONTES / "tab_4310.docx"
    try:
        _baixar_tabela_sped(docx)
    except Exception:
        if not docx.exists():
            raise RuntimeError("Não consegui baixar/converter a Tabela 4.3.10. Baixe em "
                               f"{URL_SPED}, abra no Word e salve como dados/fontes/tab_4310.docx.")
    lei = FONTES / "lei10485.html"
    try:
        req = urllib.request.Request(URL_LEI, headers={"User-Agent": "Mozilla/5.0"})
        lei.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    except Exception:
        if not lei.exists():
            raise
    regs_sped, excecoes = extrai_sped(docx)
    regs = regs_sped + extrai_lei(lei.read_bytes().decode("cp1252", "ignore"))
    df = pd.DataFrame(regs).drop_duplicates(["ncm_prefixo", "grupo", "condicao"])
    df = df[df.ncm_prefixo.str.len() >= 4].reset_index(drop=True)
    df.to_csv(ARQ_BASE, index=False, encoding="utf-8-sig", sep=";")
    meta = {"atualizado_em": datetime.now().isoformat(timespec="minutes"),
            "fontes": [URL_SPED, URL_LEI], "registros": len(df),
            "excecoes": sorted(set(excecoes)),
            "por_grupo": df.grupo.value_counts().to_dict()}
    ARQ_META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    carregar.cache_clear()
    return meta


@lru_cache(maxsize=1)
def carregar():
    if not ARQ_BASE.exists():
        return pd.DataFrame(columns=["ncm_norma", "ncm_prefixo", "grupo", "descricao", "fonte", "condicao"])
    return pd.read_csv(ARQ_BASE, sep=";", dtype=str).fillna("")


def meta():
    return json.loads(ARQ_META.read_text(encoding="utf-8")) if ARQ_META.exists() else {}


def regras_do_ncm(ncm):
    base = carregar()
    if not ncm or base.empty:
        return base.iloc[0:0]
    if any(ncm.startswith(e) for e in meta().get("excecoes", []) if e):
        return base.iloc[0:0]
    return base[[ncm.startswith(p) for p in base.ncm_prefixo]]


if __name__ == "__main__":
    print(atualizar())
