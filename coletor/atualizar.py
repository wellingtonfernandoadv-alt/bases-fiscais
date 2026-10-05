"""
Atualiza as bases normativas a partir das fontes oficiais e regenera o pacote que o
Ficha Fiscal baixa. Roda todo dia no GitHub Actions (.github/workflows/atualizar.yml)
e tambem pode rodar em qualquer PC:  python coletor/atualizar.py

Seguranca:
  - cada base e atualizada separadamente; se a fonte falhar ou vier com bem menos
    registros que a versao anterior, a versao anterior (dados/) e mantida;
  - se o conteudo de uma base nao mudou, a data de atualizacao dela tambem nao muda,
    e o pacote so ganha versao nova quando alguma base mudou de fato;
  - status.json registra o resultado de cada base; o processo termina com erro se
    alguma falhou, para o GitHub avisar por e-mail (o que deu certo e publicado).
"""
import json
import os
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from motor import base_cest, base_ibscbs, base_monofasico, base_ncm, base_st, pacote  # noqa: E402
from motor.config import DADOS, RAIZ  # noqa: E402

BASES = [
    ("cat68", "Portaria CAT 68/2019", base_st, "base_cat68"),
    ("cest", "Convênio ICMS 142/2018", base_cest, "base_cest"),
    ("ncm", "Tabela NCM", base_ncm, "base_ncm"),
    ("monofasico", "PIS/COFINS monofásico", base_monofasico, "base_monofasico"),
    ("ibscbs", "IBS/CBS (Conformidade Fácil)", base_ibscbs, "base_ibscbs"),
]
QUEDA_MAXIMA = 0.2
# Bases puladas nesta execucao (ex.: PULAR=cest no GitHub Actions: o site do CONFAZ
# recusa conexoes de fora do Brasil). Ficam com a ultima versao publicada.
PULAR = {b.strip() for b in os.environ.get("PULAR", "").split(",") if b.strip()}  # mais de 20% a menos de registros: provavel mudanca de layout da fonte


def _linhas(csv):
    return sum(1 for _ in csv.open(encoding="utf-8-sig")) - 1 if csv.exists() else 0


def atualizar_base(chave, nome, mod, arq):
    csv, meta = DADOS / f"{arq}.csv", DADOS / f"{arq}.json"
    guarda = DADOS / "_anterior"
    guarda.mkdir(exist_ok=True)
    for f in (csv, meta):
        if f.exists():
            shutil.copy2(f, guarda / f.name)
    antes = _linhas(csv)

    def restaurar():
        for f in (csv, meta):
            if (guarda / f.name).exists():
                shutil.copy2(guarda / f.name, f)

    try:
        mod.atualizar()
    except Exception as e:  # fonte fora do ar, bloqueio, layout novo...
        restaurar()
        return {"base": chave, "nome": nome, "ok": False, "erro": f"{type(e).__name__}: {e}",
                "detalhe": traceback.format_exc(limit=3), "registros": antes}
    depois = _linhas(csv)
    if antes and depois < antes * (1 - QUEDA_MAXIMA):
        restaurar()
        return {"base": chave, "nome": nome, "ok": False, "registros": antes,
                "erro": f"Extração com {depois} registros contra {antes} da versão anterior: mantida a anterior."}
    mudou = not (guarda / csv.name).exists() or (guarda / csv.name).read_bytes() != csv.read_bytes()
    if not mudou and (guarda / meta.name).exists():
        shutil.copy2(guarda / meta.name, meta)  # mesmo conteudo: mantem a data da ultima mudanca
    return {"base": chave, "nome": nome, "ok": True, "mudou": mudou, "registros": depois, "antes": antes}


def main():
    resultados = []
    for chave, nome, mod, arq in BASES:
        if chave in PULAR:
            print(f"{nome}: pulada nesta execução (PULAR)", flush=True)
            resultados.append({"base": chave, "nome": nome, "ok": True, "pulada": True,
                               "registros": _linhas(DADOS / f"{arq}.csv"),
                               "motivo": "fonte inacessível daqui; mantida a última versão publicada"})
            continue
        print(f"Atualizando {nome}...", flush=True)
        r = atualizar_base(chave, nome, mod, arq)
        print("  ", {k: v for k, v in r.items() if k != "detalhe"}, flush=True)
        resultados.append(r)
    shutil.rmtree(DADOS / "_anterior", ignore_errors=True)
    # os metas sao lidos em cache pelos modulos: zera para o pacote ver os arquivos finais
    for _, _, mod, _ in BASES:
        mod.carregar.cache_clear()
        if hasattr(mod, "vigentes"):
            mod.vigentes.cache_clear()

    anterior = RAIZ / "manifest.json"
    sha = json.loads(anterior.read_text(encoding="utf-8")).get("conteudo_sha256") if anterior.exists() else None
    manifest, publicou = pacote.gerar(RAIZ, sha)
    status = {
        "verificado_em": datetime.now().isoformat(timespec="minutes"),
        "pacote_novo": publicou,
        "versao": manifest["versao"] if publicou else json.loads(anterior.read_text(encoding="utf-8"))["versao"],
        "bases": [{k: v for k, v in r.items() if k != "detalhe"} for r in resultados],
    }
    (RAIZ / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Pacote novo:" if publicou else "Nenhuma base mudou; pacote mantido:", status["versao"])
    falhas = [r for r in resultados if not r["ok"]]
    for r in falhas:
        print(f"FALHA em {r['nome']}: {r['erro']}\n{r.get('detalhe', '')}", file=sys.stderr)
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
