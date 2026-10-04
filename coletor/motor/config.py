"""
Configuracao do coletor de bases normativas (roda no GitHub Actions ou em qualquer PC).
As regras abaixo sao as mesmas do programa Classificacao Fiscal e vao no pacote como
`parametros`, para o Ficha Fiscal aplicar.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]  # raiz do repositorio bases-fiscais
DADOS = RAIZ / "dados"  # ultima versao boa de cada base (CSV + meta JSON)
(DADOS / "fontes").mkdir(parents=True, exist_ok=True)

CSOSN_ST = {"500", "201", "202", "203"}

# Lubrificantes seguem o regime de combustiveis (Conv. ICMS 110/2007), fora da CAT 68
LUBRIFICANTES = ("27101931", "27101932", "27101938", "27101939", "27102000", "3403")

# Descricoes de itens vigentes que restringem o alcance da ST a um uso especifico
RESTRITIVA = (r"para uso na constru|pr[óo]pri[oa]s para constru|"
              r"exceto os de uso (?:automotivo|agr[íi]cola)")

# PIS/COFINS na revenda: CST 04 = monofasico (aliquota zero na revenda)
CST_MONOFASICO = "04"
