# Filtro CNAE — Estabelecimentos (Receita Federal)

App local (Streamlit) para filtrar os arquivos de **estabelecimentos** da base
pública de CNPJ da Receita Federal por **código(s) CNAE**, lendo os arquivos
brutos direto do disco com **DuckDB** — sem precisar carregar tudo na memória nem
importar para um banco. Suporta os arquivos grandes da Receita (vários GB,
dezenas de milhões de linhas).

---

## 1. Para que serve

Você tem os arquivos `*.ESTABELE` da Receita (cada um com milhões de
estabelecimentos) e quer extrair apenas os que atuam em determinada(s)
atividade(s) econômica(s) — por exemplo, todas as farmácias (`4771701`) de um
estado. O app filtra por CNAE (principal e/ou secundária), mostra uma prévia e
permite **baixar o resultado completo em CSV**.

Útil, por exemplo, para gerar listas de empresas por atividade econômica
(prospecção comercial, pesquisa de mercado, análise setorial).

> **Os dados são públicos**, disponibilizados pela Receita Federal. Este projeto
> apenas filtra arquivos que você baixa por conta própria — **nenhum dado da
> Receita é distribuído junto com o código** (ver seção "Como obter os dados").

---

## 2. Como rodar

### Pré-requisitos
- **Python 3.10+** (o código usa anotações de tipo `tuple[...]`, `list[...]`).
- **macOS ou Linux** — veja a limitação de Windows na seção 7.
- Os utilitários de sistema **`iconv`** e **`mkfifo`** (já vêm no macOS/Linux).

### Instalação (uma vez)
```bash
cd "Filter CNAE"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Execução
- **Mac (duplo clique):** `run.command` no Finder.
- **Mac/Linux (terminal):** `./run.sh`
- **Manual:** `streamlit run app.py`

O app sobe em `http://localhost:8501` e abre o navegador automaticamente.

### Uso na tela
1. **Pasta dos arquivos** — onde estão os `*.ESTABELE` (ex.: `dados brutos`).
2. **Padrão dos arquivos (glob)** — `*ESTABELE*` por padrão.
3. **Códigos CNAE** — separados por vírgula (ex.: `4754701, 4753900`).
4. **Incluir CNAE secundária** — se marcado, também acha quem tem o CNAE na lista
   de atividades secundárias.
5. **Filtrar** → barra de progresso por arquivo → prévia (até 1000 linhas) →
   **Baixar CSV completo**.

---

## 3. Como obter os dados (não vêm no repositório)

Os arquivos de estabelecimentos **não são versionados** (são públicos, grandes e
mudam todo mês). Baixe-os direto da Receita Federal:

1. Acesse os **Dados Abertos do CNPJ** da Receita Federal:
   - Pasta de download (ex.: junho/2026):
     https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9?dir=/2026-06
   - Portal geral (outros meses):
     https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/
2. Baixe os arquivos de **Estabelecimentos**
   (`Estabelecimentos0.zip`, `Estabelecimentos1.zip`, …).
3. Descompacte. Cada arquivo extraído tem nome no padrão `*.ESTABELE`.
4. Coloque-os numa pasta (ex.: `dados brutos/`) e aponte o app para ela.

Formato: CSV **sem cabeçalho**, separado por `;`, campos entre aspas, codificação
**Windows-1252 (CP1252)**, 30 colunas (ver `COLUMNS` em `app.py`).

---

## 4. Arquivos do projeto

| Arquivo            | Função |
|--------------------|--------|
| `app.py`           | Toda a aplicação (lógica + interface Streamlit). |
| `requirements.txt` | Dependências Python: `streamlit`, `duckdb`, `pandas`. |
| `run.command`      | Inicia o app no Mac via duplo clique. |
| `run.sh`           | Inicia o app no Mac/Linux via terminal. |
| `run.bat`          | Inicia no Windows (**hoje não funciona** — ver seção 7). |
| `dados brutos/`    | Onde ficam os arquivos `*.ESTABELE` da Receita (não versionados). |
| `.venv/`           | Ambiente virtual Python. |

> Os arquivos de dados são grandes (vários GB) e **não devem ir para o git**.

---

## 5. Como o `app.py` funciona (arquitetura)

O código está dividido em três blocos, na ordem do arquivo:

### a) Configuração (topo)
- `DEFAULT_DATA_DIR` — pasta padrão (sobrescrevível pela env `CNAE_DATA_DIR` ou
  pelo campo na UI).
- `DEFAULT_FILE_GLOB = "*ESTABELE*"` — quais arquivos ler.
- `COLUMNS` — **layout oficial do arquivo de estabelecimentos (30 colunas, sem
  cabeçalho)**. A ordem importa: é ela que dá nome às colunas do CSV.
- `PREVIEW_LIMIT = 1000` — quantas linhas aparecem na prévia.

### b) Leitura / query
- **`build_read_expr(path)`** — monta a expressão `read_csv(...)` do DuckDB para
  **um** arquivo. Usa `delim=';'`, `header=false`, `all_varchar=true` (tudo como
  texto, evita conversões erradas de CNPJ/CEP) e `encoding='utf-8'` (o arquivo já
  chega convertido — ver seção 6).
- **`build_where(cnaes, include_secondary)`** — monta a cláusula `WHERE`
  **parametrizada** (`?`), evitando SQL injection. Filtra
  `cnae_fiscal_principal IN (...)` e, se pedido, também a secundária via
  `list_has_any(string_split(cnae_fiscal_secundaria, ','), [...])`.
- **`_read_one_file(con, path, where, params)`** — lê e filtra **um** arquivo,
  resolvendo o problema de encoding com FIFO + `iconv` (ver seção 6).
- **`run_filter(data_dir, file_glob, cnaes, include_secondary, progress=None)`** —
  orquestra: encontra os arquivos pelo glob, chama `_read_one_file` para cada um,
  concatena os resultados num único DataFrame e retorna
  `(total, df_preview, df_full)`. O callback opcional `progress(done, total, nome)`
  alimenta a barra de progresso.

### c) UI (Streamlit)
Campos de entrada, botão **Filtrar**, barra de progresso, tabela de prévia e
botão de download. Roda de cima a baixo a cada interação (modelo do Streamlit).

---

## 6. O ponto delicado: encoding (CP1252) — LEIA antes de mexer

**Sintoma original:** ao filtrar, dava
`Invalid Input Error: File is not latin-1 encoded`.

**Causa:** os arquivos da Receita estão em **Windows-1252 (CP1252)**, não em
ISO-8859-1 (latin-1) puro. A diferença está só nos bytes **`0x80`–`0x9F`** (aspas
curvas `" "`, travessão `—`, `€`, `™`…). O leitor `latin-1` do DuckDB é estrito e
**aborta o arquivo inteiro** ao topar com qualquer desses bytes. **Nenhum** flag
(`ignore_errors`, `strict_mode=false`, `store_rejects`) pula esse erro — ele é de
decodificação, não de parsing.

**Por que não foi usado o caminho "óbvio":**
- A extensão `encodings` do DuckDB (que adicionaria `windows-1252`) **não tem
  build para macOS ARM** em nenhuma versão (testado de 1.2.x a 1.4.5 → HTTP 404).
- Pré-converter os ~30 GB para UTF-8 em disco duplicaria o armazenamento.

**Solução adotada (em `_read_one_file`):** transcodificar **CP1252 → UTF-8 em
streaming**, sem gravar nada em disco:
1. Cria um **FIFO** (named pipe) num diretório temporário.
2. Sobe um subprocesso `sh -c 'exec iconv -c -f CP1252 -t UTF-8 "arquivo" > fifo'`.
   - O `sh -c` faz o **filho** abrir o FIFO para escrita (a abertura bloqueia até
     o leitor abrir) — isso evita deadlock na thread principal do Python.
   - O `-c` descarta os 5 bytes indefinidos em CP1252 (`0x81, 0x8D, 0x8F, 0x90,
     0x9D`), raríssimos.
3. O DuckDB lê o FIFO já em UTF-8, em **uma única passada** por arquivo.

Como o FIFO só pode ser lido **uma vez**, a função faz `SELECT *` filtrado de uma
vez e deriva `total` e `preview` do DataFrame em memória (em vez de 3 queries
separadas como na versão antiga — de quebra, ficou mais rápido: lê os 30 GB uma
vez, não três).

> **Regra de ouro:** não troque `encoding='utf-8'` de volta para `'latin-1'` em
> `build_read_expr`. O arquivo chega ao DuckDB **já convertido** pelo `iconv`.

---

## 7. Limitações conhecidas / pontos de atenção

- **Windows não funciona como está.** `os.mkfifo` e `iconv` são Unix. O `run.bat`
  existe, mas a leitura vai quebrar. Para suportar Windows seria preciso outra
  estratégia de transcodificação (ex.: converter via Python lendo em `cp1252` e
  reescrevendo em UTF-8, ou pré-converter os arquivos). Ver seção 8.
- **Resultado vai todo para a memória.** `run_filter` concatena todas as linhas
  filtradas num DataFrame pandas. Para CNAEs muito comuns (milhões de matches) o
  uso de RAM pode ser alto. Filtros normais (atividades específicas) são
  tranquilos.
- **Reconversão a cada filtragem.** O `iconv` roda toda vez que você filtra (não
  há cache em disco). Para ~30 GB são alguns minutos por filtragem — a barra de
  progresso mostra o andamento. Se for filtrar com muita frequência, ver seção 8.
- **Layout fixo de 30 colunas.** Se a Receita mudar o layout do arquivo
  `ESTABELE`, é preciso atualizar a lista `COLUMNS`.

---

## 8. Ideias para evoluir

- **Cache UTF-8 em disco:** converter cada `*.ESTABELE` uma vez para um
  `.cache_utf8/` (pulando se já existir e a data/tamanho baterem) e ler o cache
  com o DuckDB. Filtragens seguintes ficam quase instantâneas. Custo: ~30 GB
  extras de disco.
- **Converter para Parquet:** transformar os arquivos em Parquet (colunar,
  comprimido) seria muito mais rápido para filtrar e menor em disco — melhor
  formato para evoluir o projeto se as filtragens forem recorrentes.
- **Suporte a Windows:** implementar a transcodificação em Python puro (sem
  `iconv`/FIFO) para rodar em qualquer SO.
- **Mais filtros na UI:** por UF, município, situação cadastral (ativa/baixada),
  data de início — todas são colunas já disponíveis em `COLUMNS`.
- **Cruzar com outras tabelas:** a pasta também tem `*.SOCIOCSV` (sócios) e
  `*.MUNICCSV` (municípios). Dá para enriquecer o resultado (nome de município,
  quadro societário) com `JOIN` no DuckDB.
- **Exportar colunas selecionadas:** hoje o CSV sai com as 30 colunas; permitir
  escolher quais exportar deixaria o arquivo de leads mais enxuto.

---

## 9. Publicando no GitHub

> ⚠️ **Atenção crítica antes do primeiro `push`.**
> Hoje o repositório git fica na **pasta-mãe** (`uailabs projects`), que contém
> configurações pessoais e outros projetos. **Não publique essa pasta inteira.**
> Crie um repositório novo **dentro de `Filter CNAE`**, isolado:
>
> ```bash
> cd "Filter CNAE"
> git init
> git add .
> git commit -m "Filtro CNAE — versão inicial"
> # crie o repo vazio no GitHub e então:
> git remote add origin git@github.com:SEU_USUARIO/filter-cnae.git
> git push -u origin main
> ```

**O `.gitignore` já protege** os itens sensíveis/pesados: a pasta `dados brutos/`
e arquivos `*.ESTABELE`/`*.csv`/`*.parquet`, a `.venv/`, caches, `.DS_Store` e
`secrets.toml` do Streamlit.

**Checklist antes de publicar:**
- [ ] Rodar `git status` e confirmar que **nenhum** arquivo de dados (`*.ESTABELE`,
      CSVs grandes) está sendo adicionado.
- [ ] Confirmar que `.venv/` **não** aparece.
- [ ] Conferir que não há credenciais, e-mails ou caminhos pessoais no código
      (o `app.py` usa caminho relativo por padrão — ok).
- [ ] Incluir um arquivo `LICENSE` (ver seção 10).

---

## 10. Licença

Este projeto usa a licença **MIT** (arquivo [`LICENSE`](LICENSE)) — permissiva e
simples: qualquer pessoa pode usar, copiar, modificar e distribuir o código,
desde que mantenha o aviso de copyright. O detentor do copyright é **uaiLabs**
(altere o nome no arquivo `LICENSE` se quiser).

Lembre-se: a licença cobre **o código**, não os dados da Receita (que são
públicos e seguem os termos dos Dados Abertos do governo).

---

## 11. Referências rápidas

- **Layout dos arquivos da Receita (CNPJ):**
  https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf
- **DuckDB `read_csv`:** https://duckdb.org/docs/data/csv/overview
- **Streamlit:** https://docs.streamlit.io
