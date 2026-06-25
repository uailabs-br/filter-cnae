"""
Filtro de CNAE — Receita Federal (estabelecimentos)

App local em Streamlit para filtrar os arquivos de "estabelecimentos" da
Receita Federal por códigos CNAE, lendo os arquivos brutos direto do disco
com DuckDB (suporta arquivos grandes, milhões de linhas).
"""

import glob
import io
import os
import shutil
import subprocess
import tempfile

import duckdb
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

# Pasta padrão onde estão os arquivos de estabelecimentos.
# Pode ser sobrescrita pela variável de ambiente CNAE_DATA_DIR ou pelo campo na UI.
DEFAULT_DATA_DIR = os.environ.get(
    "CNAE_DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados brutos"),
)

# Padrão (glob) que identifica os arquivos de estabelecimentos dentro da pasta.
DEFAULT_FILE_GLOB = "*ESTABELE*"

# Layout oficial do arquivo de estabelecimentos (30 colunas, sem cabeçalho).
COLUMNS = [
    "cnpj_basico",
    "cnpj_ordem",
    "cnpj_dv",
    "identificador_matriz_filial",
    "nome_fantasia",
    "situacao_cadastral",
    "data_situacao_cadastral",
    "motivo_situacao_cadastral",
    "nome_cidade_exterior",
    "pais",
    "data_inicio_atividade",
    "cnae_fiscal_principal",
    "cnae_fiscal_secundaria",
    "tipo_logradouro",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "cep",
    "uf",
    "municipio",
    "ddd_1",
    "telefone_1",
    "ddd_2",
    "telefone_2",
    "ddd_fax",
    "fax",
    "correio_eletronico",
    "situacao_especial",
    "data_situacao_especial",
]

PREVIEW_LIMIT = 1000


# ---------------------------------------------------------------------------
# Leitura / query
# ---------------------------------------------------------------------------


def build_read_expr(path: str) -> str:
    """Monta a expressão read_csv para UM arquivo (já em UTF-8, via FIFO)."""
    names = ", ".join(f"'{c}'" for c in COLUMNS)
    return (
        "read_csv("
        f"'{path}', "
        "delim=';', "
        "header=false, "
        "quote='\"', "
        "escape='\"', "
        "encoding='utf-8', "
        "all_varchar=true, "
        f"names=[{names}]"
        ")"
    )


def build_where(cnaes: list[str], include_secondary: bool) -> tuple[str, list[str]]:
    """Monta a cláusula WHERE parametrizada e a lista de parâmetros."""
    placeholders = ", ".join(["?"] * len(cnaes))
    params = list(cnaes)

    where = f"cnae_fiscal_principal IN ({placeholders})"
    if include_secondary:
        # cnae_fiscal_secundaria é uma lista separada por vírgula dentro do campo.
        # Quebramos em lista e checamos se algum dos CNAEs informados está presente.
        sec_placeholders = ", ".join(["?"] * len(cnaes))
        where += (
            " OR list_has_any("
            "string_split(cnae_fiscal_secundaria, ','), "
            f"[{sec_placeholders}]"
            ")"
        )
        params += list(cnaes)
    return where, params


def _read_one_file(con, path: str, where: str, params: list[str]):
    """Lê e filtra UM arquivo, transcodificando CP1252->UTF-8 em streaming.

    Os arquivos da Receita estão em Windows-1252 (CP1252), que o DuckDB não lê
    nativamente (o leitor latin-1 aborta nos bytes 0x80-0x9F). Em vez de
    reescrever ~30 GB em disco, alimentamos um FIFO com `iconv` e o DuckDB lê o
    pipe já em UTF-8, numa única passada por arquivo.
    """
    tmpdir = tempfile.mkdtemp(prefix="cnae_fifo_")
    fifo = os.path.join(tmpdir, "data.csv")
    os.mkfifo(fifo)

    # O `sh -c` abre o FIFO para escrita no processo filho (bloqueia até o
    # DuckDB abrir para leitura), evitando deadlock na thread principal.
    # `-c` descarta os poucos bytes indefinidos em CP1252 (0x81, 0x8D, ...).
    writer = subprocess.Popen(
        ["sh", "-c", 'exec iconv -c -f CP1252 -t UTF-8 "$1" > "$2"', "sh", path, fifo]
    )
    try:
        read_expr = build_read_expr(fifo)
        df = con.execute(
            f"SELECT * FROM {read_expr} WHERE {where}", params
        ).fetchdf()
    finally:
        # O DuckDB lê o stream inteiro (scan com WHERE), então o iconv termina.
        writer.wait()
        shutil.rmtree(tmpdir, ignore_errors=True)
    return df


def run_filter(
    data_dir: str,
    file_glob: str,
    cnaes: list[str],
    include_secondary: bool,
    progress=None,
):
    """Filtra todos os arquivos da pasta e retorna (total, df_preview, df_full)."""
    files = sorted(glob.glob(os.path.join(data_dir, file_glob)))
    if not files:
        raise FileNotFoundError(
            f"Nenhum arquivo corresponde a '{file_glob}' em {data_dir}"
        )

    where, params = build_where(cnaes, include_secondary)

    con = duckdb.connect()
    frames = []
    try:
        for i, path in enumerate(files):
            if progress is not None:
                progress(i, len(files), os.path.basename(path))
            frames.append(_read_one_file(con, path, where, params))
        if progress is not None:
            progress(len(files), len(files), "")
    finally:
        con.close()

    df_full = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=COLUMNS)
    )
    total = len(df_full)
    df_preview = df_full.head(PREVIEW_LIMIT)
    return total, df_preview, df_full


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


st.set_page_config(page_title="Filtro de CNPJs por CNAE", layout="wide")
st.title("Filtro de CNPJs por CNAE")
st.caption(
    "Filtre os arquivos de estabelecimentos da Receita Federal por código CNAE "
    "e baixe o resultado em CSV."
)

# Formulário numa coluna estreita; a tabela de resultados usa a largura total.
form_col, _ = st.columns([3, 2])

with form_col:
    st.subheader("1. Selecione a pasta com os arquivos brutos")

    data_dir = st.text_input(
        "Cole ou digite o caminho da pasta",
        value=DEFAULT_DATA_DIR,
        help="Pasta onde estão os arquivos brutos de estabelecimentos da Receita Federal. "
        "Dica: no Finder, clique com o botão direito na pasta › Obter Informações para ver o caminho.",
    )

    if os.path.isdir(data_dir):
        n_files = len(glob.glob(os.path.join(data_dir, DEFAULT_FILE_GLOB)))
        if n_files:
            st.success(f"✅ {n_files} arquivo(s) encontrado(s) na pasta.")
        else:
            st.warning("⚠️ Nenhum arquivo de estabelecimentos encontrado nesta pasta.")
    else:
        st.info("Cole o caminho de uma pasta válida.")

    with st.expander("Opções avançadas"):
        file_glob = st.text_input(
            "Padrão dos arquivos (glob)",
            value=DEFAULT_FILE_GLOB,
            help="Padrão usado para localizar os arquivos de estabelecimentos na pasta.",
        )

    st.subheader("2. Informe os códigos CNAE")

    cnae_input = st.text_input(
        "Códigos CNAE",
        placeholder="ex.: 4754701, 4753900",
        help="Use apenas números. Para mais de um código, separe por vírgula.",
    )
    st.caption("ℹ️ Apenas números (sem pontos, traços ou barras).")
    include_secondary = st.checkbox("Incluir CNAE secundária", value=True)

    filtrar = st.button("Filtrar", type="primary")

if filtrar:
    cnaes = [c.strip() for c in cnae_input.split(",") if c.strip()]
    invalid = [c for c in cnaes if not c.isdigit()]

    if not cnaes:
        st.warning("Informe pelo menos um código CNAE.")
    elif invalid:
        st.error(
            "O código CNAE deve conter apenas números. "
            f"Valor(es) inválido(s): {', '.join(invalid)}"
        )
    elif not os.path.isdir(data_dir):
        st.error(f"Pasta não encontrada: {data_dir}")
    else:
        bar = st.progress(0.0, text="Preparando…")

        def _progress(done: int, total_files: int, name: str):
            frac = done / total_files if total_files else 1.0
            label = (
                f"Lendo arquivo {done + 1}/{total_files}: {name}"
                if name
                else "Finalizando…"
            )
            bar.progress(min(frac, 1.0), text=label)

        with st.spinner("Filtrando…"):
            try:
                total, df_preview, df_full = run_filter(
                    data_dir, file_glob, cnaes, include_secondary, progress=_progress
                )
            except Exception as exc:  # noqa: BLE001
                bar.empty()
                st.error(f"Erro ao consultar os arquivos: {exc}")
            else:
                bar.empty()
                st.success(f"{total:,} registro(s) encontrado(s).".replace(",", "."))

                if total > PREVIEW_LIMIT:
                    st.caption(f"Mostrando os primeiros {PREVIEW_LIMIT} registros na prévia.")
                st.dataframe(df_preview, use_container_width=True)

                csv_buf = io.StringIO()
                df_full.to_csv(csv_buf, index=False, sep=";")
                st.download_button(
                    "Baixar CSV completo",
                    data=csv_buf.getvalue().encode("utf-8-sig"),
                    file_name="estabelecimentos_filtrados.csv",
                    mime="text/csv",
                )
