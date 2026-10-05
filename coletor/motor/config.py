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

# ---- IBS/CBS (LC 214/2025, com a LC 227/2026) -------------------------------------------
# Imposto Seletivo: Anexo XVII da LC 214/2025 (art. 409). Cada regra: prefixo de NCM,
# codigos excluidos, categoria e condicao. Fumigenos e bebidas alcoolicas so em embalagem
# primaria destinada ao consumidor final (art. 409, par. 2o).
IMPOSTO_SELETIVO = [
    {"prefixo": "8703", "excecoes": [], "categoria": "Veículos",
     "condicao": "Ressalvados os veículos para uso operacional das Forças Armadas ou da Segurança Pública"},
    *[{"prefixo": p, "excecoes": [], "categoria": "Veículos",
       "condicao": "Exceto os caminhões; ressalvados os de uso operacional das Forças Armadas ou da Segurança Pública"}
      for p in ("870421", "870431", "87044100", "87045100", "87046000", "87049000")],
    {"prefixo": "8802", "excecoes": ["88026000"], "categoria": "Aeronaves",
     "condicao": "Ressalvadas as de uso operacional das Forças Armadas ou da Segurança Pública"},
    {"prefixo": "8903", "excecoes": [], "categoria": "Embarcações",
     "condicao": "Só embarcações com motor; ressalvadas as de uso operacional das Forças Armadas ou da Segurança Pública"},
    *[{"prefixo": p, "excecoes": [], "categoria": "Produtos fumígenos",
       "condicao": "Só em embalagem primária destinada ao consumidor final (art. 409, § 2º)"}
      for p in ("2401", "2402", "2403", "2404")],
    *[{"prefixo": p, "excecoes": [], "categoria": "Bebidas alcoólicas",
       "condicao": "Só em embalagem primária destinada ao consumidor final (art. 409, § 2º)"}
      for p in ("2203", "2204", "2205", "2206", "2208")],
    {"prefixo": "22021000", "excecoes": [], "categoria": "Bebidas açucaradas", "condicao": ""},
    *[{"prefixo": p, "excecoes": [], "categoria": "Bens minerais", "condicao": ""}
      for p in ("2601", "27090010", "27111100", "27112100")],
]
IMPOSTO_SELETIVO_FONTE = "LC 214/2025, art. 409, § 1º, e Anexo XVII"

# Combustiveis do regime monofasico (art. 172): a lei lista os produtos, nao os NCM
# (gasolina e correntes, EAC, diesel e correntes, biodiesel, GLP/GLGN, EHC, QAV, oleo
# combustivel, gas natural processado, biometano, GNV e outros autorizados pela ANP).
# Os prefixos abaixo so marcam o item para conferencia; o enquadramento depende do produto.
COMBUSTIVEIS_PREFIXOS = ["271012", "271019", "2711", "2207", "3826"]
COMBUSTIVEIS_FONTE = "LC 214/2025, arts. 172 a 180 (redação da LC 227/2026)"
