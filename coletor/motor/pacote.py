"""
Pacote de bases normativas para o Ficha Fiscal (e qualquer outro aplicativo).

Junta num unico JSON compactado (gzip) as bases que este programa extrai das fontes
oficiais, mais os parametros das regras, com versao e verificacao de integridade:

  manifest.json   {formato, versao, gerado_em, sha256, tamanho, conteudo_sha256, bases: {...}}
  bases.json.gz   {formato, versao, parametros, bases: {nome: {meta, colunas, linhas}}}

Cada base vai em formato tabular (colunas + linhas) para ficar pequeno. A descricao
completa da NCM (caminho capitulo > ... > item) e recalculada no aparelho.
"""
import gzip
import hashlib
import json
from datetime import datetime

from motor import base_cest, base_ibscbs, base_monofasico, base_ncm, base_st
from motor.config import (COMBUSTIVEIS_FONTE, COMBUSTIVEIS_PREFIXOS, CSOSN_ST, CST_MONOFASICO,
                          IMPOSTO_SELETIVO, IMPOSTO_SELETIVO_FONTE, LUBRIFICANTES, RESTRITIVA)

FORMATO = 1


def _tabela(df, colunas, meta):
    d = df[colunas].fillna("").astype(str)
    return {"meta": meta, "colunas": colunas, "linhas": d.values.tolist()}


def montar():
    """Conteudo do pacote (sem data de geracao, para o hash so mudar se as bases mudarem)."""
    mono_meta = base_monofasico.meta()
    return {
        "formato": FORMATO,
        "parametros": {
            "lubrificantes": list(LUBRIFICANTES),
            "descricao_restritiva": RESTRITIVA,
            "csosn_st": sorted(CSOSN_ST),
            "cst_st_regime_normal": ["10", "30", "60", "70"],
            "cst_monofasico": CST_MONOFASICO,
            "pis_monofasico_compra": ["02", "04"],
            "trib_normal": {"cst": "0", "csosn": "102", "cfop_int": "5102", "cfop_ext": "6102"},
            "trib_st": {"cst": "60", "csosn": "500", "cfop_int": "5405", "cfop_ext": "6404"},
            "pis_monofasico_ate": "2026-12-31",  # PIS/COFINS extintos em 2027 (EC 132/2023)
            "imposto_seletivo": IMPOSTO_SELETIVO,
            "imposto_seletivo_fonte": IMPOSTO_SELETIVO_FONTE,
            "combustiveis_prefixos": COMBUSTIVEIS_PREFIXOS,
            "combustiveis_fonte": COMBUSTIVEIS_FONTE,
        },
        "bases": {
            "cat68": _tabela(base_st.carregar(),
                             ["anexo", "segmento", "item", "cest", "ncm_norma", "ncm_prefixo",
                              "descricao_norma", "situacao", "revogado_por", "sem_st_desde"],
                             {**base_st.meta(), "nome": "Portaria CAT 68/2019 (ICMS-ST SP)"}),
            "cest": _tabela(base_cest.carregar(),
                            ["anexo", "segmento", "item", "cest", "ncm_norma", "ncm_prefixo", "descricao_norma"],
                            {**base_cest.meta(), "nome": "Convênio ICMS 142/2018 (CEST)"}),
            "monofasico": _tabela(base_monofasico.carregar(),
                                  ["ncm_norma", "ncm_prefixo", "grupo", "descricao", "fonte", "condicao"],
                                  {"atualizado_em": mono_meta.get("atualizado_em", ""),
                                   "fontes": mono_meta.get("fontes", []),
                                   "excecoes": mono_meta.get("excecoes", []),
                                   "nome": "PIS/COFINS monofásico (SPED 4.3.10 e Lei 10.485/2002)"}),
            "ncm": _tabela(base_ncm.carregar(),
                           ["codigo", "digitos", "nivel", "descricao", "inicio", "fim", "ato"],
                           {**{k: v for k, v in base_ncm.meta().items() if k not in ("incluidos", "excluidos")},
                            "nome": "Tabela NCM (Siscomex)"}),
            "ibscbs": _tabela(base_ibscbs.carregar(), base_ibscbs.COLUNAS,
                              {**{k: v for k, v in base_ibscbs.meta().items() if k not in ("incluidos", "excluidos")},
                               "nome": "IBS/CBS — classificação tributária (Conformidade Fácil)"}),
            "ibscbs_itens": _tabela(base_ibscbs.carregar_itens(), base_ibscbs.COLUNAS_ITENS,
                                    {"atualizado_em": base_ibscbs.meta().get("atualizado_em", ""),
                                     "fonte": base_ibscbs.URL,
                                     "nome": "IBS/CBS — NCM e NBS por cClassTrib (anexos da LC 214)"}),
        },
    }


def gerar(destino_dir, anterior_sha=None):
    """Grava manifest.json e bases.json.gz em destino_dir. Devolve (manifest, mudou)."""
    conteudo = montar()
    canon = json.dumps(conteudo, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    conteudo_sha = hashlib.sha256(canon).hexdigest()
    if anterior_sha == conteudo_sha:
        return None, False
    agora = datetime.now()
    versao = agora.strftime("%Y.%m.%d-%H%M")
    pacote = {**conteudo, "versao": versao, "gerado_em": agora.isoformat(timespec="minutes")}
    dados = gzip.compress(json.dumps(pacote, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                          compresslevel=9, mtime=0)
    (destino_dir / "bases.json.gz").write_bytes(dados)
    manifest = {
        "formato": FORMATO, "versao": versao, "gerado_em": pacote["gerado_em"],
        "arquivo": "bases.json.gz", "tamanho": len(dados), "sha256": hashlib.sha256(dados).hexdigest(),
        "conteudo_sha256": conteudo_sha,
        "bases": {k: {"nome": v["meta"].get("nome"), "registros": len(v["linhas"]),
                      "atualizado_em": v["meta"].get("atualizado_em", ""),
                      **({"vigencia": v["meta"]["vigencia"]} if "vigencia" in v["meta"] else {})}
                  for k, v in conteudo["bases"].items()},
    }
    (destino_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest, True
