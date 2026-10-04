# Bases fiscais

Pacote de bases normativas usado pelo aplicativo **Ficha Fiscal** para a revisão tributária de
cadastros de produtos (ICMS-ST de São Paulo, CEST, PIS/COFINS monofásico e NCM).

Contém **somente legislação pública**, extraída e organizada a partir das fontes oficiais:

| Base | Fonte |
|---|---|
| Portaria CAT 68/2019 — mercadorias sujeitas à ST em SP, com itens vigentes e revogados e a data de efeito | [Sefaz-SP](https://legislacao.fazenda.sp.gov.br/Paginas/Portaria-CAT-68-de-2019.aspx) |
| Convênio ICMS 142/2018 — tabela de CEST (Anexos II a XXVI, redação vigente) | [CONFAZ](https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18) |
| PIS/COFINS monofásico — Tabela 4.3.10 do SPED e Lei 10.485/2002, Anexos I e II | [SPED/RFB](http://sped.rfb.gov.br/item/show/1638), [Planalto](https://www.planalto.gov.br/ccivil_03/leis/2002/l10485.htm) |
| Tabela NCM vigente | [Portal Único Siscomex](https://portalunico.siscomex.gov.br/classif/) |

## Arquivos

- `manifest.json` — versão, data, tamanho e SHA-256 do pacote; resumo de cada base.
- `bases.json.gz` — o pacote (JSON compactado com gzip). Cada base vem como `colunas` + `linhas`,
  com `meta` (data de atualização e fonte). `parametros` traz as regras fixas usadas na análise.

O aplicativo compara a `versao` do manifest com a que tem guardada e, se houver nova, baixa o
pacote e confere o SHA-256 antes de usar.

Gerado pelo programa Classificação Fiscal (`publicar_bases.py`). Não há dados de clientes aqui.
