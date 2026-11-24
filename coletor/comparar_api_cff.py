"""
Compara a tabela de cClassTrib da API oficial do Conformidade Facil (SVRS) com a base que o
coletor monta a partir da pagina publica (dados/base_ibscbs.csv).

Precisa rodar num PC no Brasil: a API exige certificado digital ICP-Brasil (A1, arquivo .pfx).

Dois jeitos de usar:

  1) O script chama a API com o certificado:
       python coletor\\comparar_api_cff.py --pfx C:\\caminho\\certificado.pfx
     (a senha do certificado e pedida na hora; nao fica gravada em lugar nenhum)

  2) Sem Python mexendo no certificado: abra no Chrome/Edge (com o certificado instalado)
       https://cff.svrs.rs.gov.br/api/v1/consultas/classTrib
     salve a pagina como "classTrib.json" e rode:
       python coletor\\comparar_api_cff.py --arquivo C:\\caminho\\classTrib.json

O resultado vai para dados/fontes/comparacao_api_cff/ (pasta fora do git):
  resumo.txt        quantos codigos batem, quantos divergem e em que campo
  divergencias.csv  um registro por diferenca (cClassTrib, campo, valor nossa base, valor API)
  api_bruta.json    a resposta da API, como veio
"""
import argparse
import getpass
import json
import os
import ssl
import sys
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motor import base_ibscbs  # noqa: E402
from motor.config import DADOS  # noqa: E402

URL_API = "https://cff.svrs.rs.gov.br/api/v1/consultas/classTrib"
SAIDA = DADOS / "fontes" / "comparacao_api_cff"

# campos comparados (os de enquadramento; url e data de publicacao ficam de fora)
CAMPOS = ["cst", "descricao", "red_ibs", "red_cbs", "tipo_aliquota", "nfe", "nfce", "nfse",
          "anexo", "inicio", "fim"]


def baixar_api(pfx, senha):
    """GET na API com autenticacao mutua TLS usando o certificado A1 (.pfx)."""
    try:
        from cryptography.hazmat.primitives.serialization import (Encoding, NoEncryption,
                                                                  PrivateFormat, pkcs12)
    except ImportError:
        sys.exit("Falta o pacote 'cryptography': rode  pip install cryptography  e tente de novo.")
    chave, cert, cadeia = pkcs12.load_key_and_certificates(Path(pfx).read_bytes(), senha.encode())
    pem = chave.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    pem += cert.public_bytes(Encoding.PEM)
    for c in cadeia or []:
        pem += c.public_bytes(Encoding.PEM)
    # o ssl do Python so le certificado de arquivo: grava temporario e apaga logo em seguida
    fd, tmp = tempfile.mkstemp(suffix=".pem")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(tmp)
    finally:
        os.remove(tmp)
    req = urllib.request.Request(URL_API, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, context=ctx, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def _chave(d, *nomes):
    """Le um campo sem depender de maiusculas/minusculas (o layout da API pode variar)."""
    baixo = {k.lower(): v for k, v in d.items()}
    for n in nomes:
        if n.lower() in baixo:
            return baixo[n.lower()]
    return None


def normalizar(dados):
    """Converte a resposta da API para o layout de base_ibscbs.csv."""
    if isinstance(dados, dict):  # resposta embrulhada: {"dados": [...]} ou parecido
        listas = [v for v in dados.values() if isinstance(v, list)]
        if not listas:
            raise RuntimeError("Resposta da API sem lista de registros; veja api_bruta.json")
        dados = listas[0]
    if dados and _chave(dados[0], "ClassificacoesTributarias") is not None:
        # mesmo formato da pagina publica: lista de CST com as classificacoes dentro
        df, _ = base_ibscbs.extrai(dados)
        return df
    # formato plano: um registro por cClassTrib
    linhas = []
    for d in dados:
        def g(*n):
            return _chave(d, *n)
        linhas.append({
            "cst": g("Cst", "CST"), "descricao": base_ibscbs._texto(g("NomeClassTrib", "Descricao")),
            "cclasstrib": g("CodClassTrib", "cClassTrib", "ClassTrib"),
            "red_ibs": f'{float(g("PercRedIbs", "pRedIBS") or 0):g}',
            "red_cbs": f'{float(g("PercRedCbs", "pRedCBS") or 0):g}',
            "tipo_aliquota": g("TipoAliq", "TipoAliquota") or "",
            "nfe": "S" if g("IndNfe", "IndNFe") else "N", "nfce": "S" if g("IndNfce", "IndNFCe") else "N",
            "nfse": "S" if g("IndNfse", "IndNFSe") else "N",
            "anexo": g("NroAnexo", "Anexo") or "",
            "inicio": base_ibscbs._data(g("DthIniVig", "IniVig")), "fim": base_ibscbs._data(g("DthFimVig", "FimVig")),
        })
    return pd.DataFrame(linhas)


def comparar(nossa, api):
    nossa = nossa.astype(str).set_index("cclasstrib")
    api = api.astype(str).set_index("cclasstrib")
    so_nossa = sorted(set(nossa.index) - set(api.index))
    so_api = sorted(set(api.index) - set(nossa.index))
    difs = []
    for c in sorted(set(nossa.index) & set(api.index)):
        for campo in CAMPOS:
            if campo not in api.columns:
                continue
            a, b = str(nossa.at[c, campo]).strip(), str(api.at[c, campo]).strip()
            if a in ("nan", "None"):
                a = ""
            if b in ("nan", "None"):
                b = ""
            if a != b:
                difs.append({"cclasstrib": c, "campo": campo, "nossa_base": a, "api": b})
    return so_nossa, so_api, pd.DataFrame(difs, columns=["cclasstrib", "campo", "nossa_base", "api"])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pfx", help="certificado A1 (.pfx) para chamar a API")
    g.add_argument("--arquivo", help="JSON da API ja salvo pelo navegador")
    a = p.parse_args()

    SAIDA.mkdir(parents=True, exist_ok=True)
    if a.pfx:
        dados = baixar_api(a.pfx, getpass.getpass("Senha do certificado: "))
    else:
        dados = json.loads(Path(a.arquivo).read_text(encoding="utf-8-sig"))
    (SAIDA / "api_bruta.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")

    nossa = base_ibscbs.carregar()
    api = normalizar(dados)
    so_nossa, so_api, difs = comparar(nossa, api)
    difs.to_csv(SAIDA / "divergencias.csv", index=False, sep=";", encoding="utf-8-sig")

    comuns = len(set(nossa.cclasstrib) & set(api.cclasstrib))
    com_dif = difs.cclasstrib.nunique()
    meta = base_ibscbs.meta()
    linhas = [
        f"Comparação API Conformidade Fácil x base do coletor — {datetime.now():%d/%m/%Y %H:%M}",
        f"Nossa base: {len(nossa)} cClassTrib (atualizada em {meta.get('atualizado_em', '?')}, "
        f"publicação mais recente {meta.get('publicacao_mais_recente', '?')})",
        f"API:        {len(api)} cClassTrib",
        "",
        f"Em comum: {comuns}  |  idênticos: {comuns - com_dif}  |  com diferença: {com_dif}",
        f"Só na nossa base ({len(so_nossa)}): {', '.join(so_nossa) or '-'}",
        f"Só na API ({len(so_api)}): {', '.join(so_api) or '-'}",
    ]
    campos_api = [c for c in CAMPOS if c in api.columns]
    if campos_api != CAMPOS:
        linhas.append(f"Campos que a API não trouxe (não comparados): {', '.join(sorted(set(CAMPOS) - set(campos_api)))}")
    if len(difs):
        linhas += ["", "Diferenças por campo:"]
        linhas += [f"  {k}: {v}" for k, v in difs.campo.value_counts().items()]
    veredito = ("BATEM: a base do coletor é igual à API." if not (so_nossa or so_api or len(difs))
                else "HÁ DIFERENÇAS: veja divergencias.csv.")
    linhas += ["", veredito]
    texto = "\n".join(linhas)
    (SAIDA / "resumo.txt").write_text(texto + "\n", encoding="utf-8")
    print(texto)
    print(f"\nArquivos em {SAIDA}")


if __name__ == "__main__":
    main()
