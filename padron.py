# app.py - Padrón Unidad Roja y Blanca (STREAMLIT CLOUD COMPATIBLE - SIN OCR)
import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO, StringIO
from fpdf import FPDF
import matplotlib.pyplot as plt
import seaborn as sns
import warnings

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Unidad Roja y Blanca - Padrón", layout="wide")
DEFAULT_LIST_NAME = "unidad roja y blanca"

# ---------------------------------------------------
# PARSEADOR PARA PDFs CON TEXTO
# ---------------------------------------------------
def parse_line_by_pattern(line):
    line = line.strip()
    if not line:
        return None

    line = re.sub(r"\s+", " ", line)
    parts = line.split(" ")

    idx = parts[0] if parts[0].isdigit() else ""

    dni = ""
    for p in parts:
        if re.fullmatch(r"\d{6,11}", p):
            dni = p
            break

    if dni:
        rest = line.split(dni, 1)[1].strip()
    else:
        rest = " ".join(parts[1:]).strip()

    tokens = rest.split(" ")
    if len(tokens) >= 3:
        apellido = " ".join(tokens[:2])
        nombre = " ".join(tokens[2:])
    else:
        apellido = tokens[0] if tokens else ""
        nombre = " ".join(tokens[1:]) if len(tokens) >= 2 else ""

    return {
        "n": idx,
        "dni": dni,
        "apellido": apellido.title().strip(),
        "nombre": nombre.title().strip()
    }

def parse_text_block_to_df(text):
    rows = []
    for line in text.splitlines():
        p = parse_line_by_pattern(line)
        if p and (p["dni"] or p["apellido"] or p["nombre"]):
            rows.append(p)
    return pd.DataFrame(rows)

# ---------------------------------------------------
# LEER PDF (SOLO TEXTO)
# ---------------------------------------------------
def read_pdf_text(pdf_bytes):
    text = ""
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except:
        text = ""
    return text

# ---------------------------------------------------
# NORMALIZAR EXCEL / CSV
# ---------------------------------------------------
def normalize_excel_df(df):
    out = pd.DataFrame()
    out["n"] = df.index.astype(str)

    col_dni = next((c for c in df.columns if "dni" in c.lower()), None)
    out["dni"] = df[col_dni].astype(str).str.replace(r"\D", "", regex=True) if col_dni else ""

    col_ap = next((c for c in df.columns if "apell" in c.lower()), None)
    col_no = next((c for c in df.columns if "nom" in c.lower()), None)

    out["apellido"] = df[col_ap].astype(str).str.title().str.strip() if col_ap else ""
    out["nombre"] = df[col_no].astype(str).str.title().str.strip() if col_no else ""

    # Mails: domicilio/dirección también se interpreta como mail
    col_mail = next((c for c in df.columns if any(x in c.lower() for x in ["mail","email","domicilio","direccion"])), None)
    out["mail"] = df[col_mail].astype(str).str.strip() if col_mail else ""

    # fecha ingreso
    col_ing = next((c for c in df.columns if any(x in c.lower() for x in ["fecha","ingreso","inscrip","alta"])), None)
    out["fecha_ingreso"] = pd.to_datetime(df[col_ing], errors="ignore") if col_ing else ""

    return out

# ---------------------------------------------------
# CARGAR PDF/EXCEL/CSV
# ---------------------------------------------------
def load_file_to_df(uploaded_file):
    name = uploaded_file.name.lower()
    raw = uploaded_file.read()

    # PDF con texto (NO OCR)
    if name.endswith(".pdf"):
        text = read_pdf_text(raw)
        df = parse_text_block_to_df(text)
        if not df.empty:
            df["mail"] = ""
            df["fecha_ingreso"] = ""
        return df

    # Excel
    if name.endswith((".xlsx",".xls")):
        df_excel = pd.read_excel(BytesIO(raw), engine="openpyxl")
        return normalize_excel_df(df_excel)

    # CSV
    if name.endswith(".csv"):
        df_csv = pd.read_csv(StringIO(raw.decode("utf-8", errors="ignore")))
        return normalize_excel_df(df_csv)

    return pd.DataFrame()

# ---------------------------------------------------
# UI PRINCIPAL
# ---------------------------------------------------
st.title("📋 Sistema de Militancia – Unidad Roja y Blanca")
st.write("Compatible con PDF (texto), Excel y CSV. OCR deshabilitado para Streamlit Cloud.")

st.subheader("📤 Cargar 1 o más padrones")
files = st.file_uploader("Subir padrones", type=["pdf","xlsx","xls","csv"], accept_multiple_files=True)

if not files:
    st.stop()

dfs = []
for f in files:
    df_temp = load_file_to_df(f)
    if not df_temp.empty:
        dfs.append(df_temp)

if not dfs:
    st.error("Ningún archivo pudo procesarse.")
    st.stop()

# UNIFICAR
df = pd.concat(dfs, ignore_index=True)
df["dni"] = df["dni"].astype(str).str.replace(r"\D","",regex=True)
df["apellido"] = df["apellido"].astype(str).str.title().str.strip()
df["nombre"] = df["nombre"].astype(str).str.title().str.strip()

st.success(f"{len(dfs)} padrones cargados correctamente.")
st.dataframe(df.head(200))

# ---------------------------------------------------
# CRUZAR PADRONES AUTOMÁTICAMENTE (3 o más)
# ---------------------------------------------------
st.header("🔗 Cruce automático entre padrones")

if len(dfs) >= 2:
    st.write(f"Se cruzarán **{len(dfs)} padrones** por DNI.")

    # Padrones únicos por DNI
    padrones_con_dni = [d[d["dni"].astype(bool)] for d in dfs]

    comunes = padrones_con_dni[0]
    for d in padrones_con_dni[1:]:
        comunes = comunes[comunes["dni"].isin(d["dni"])]

    st.subheader(f"🎯 Coincidencias encontradas en los {len(dfs)} padrones")
    st.write(f"Total coincidencias: **{len(comunes)}**")
    st.dataframe(comunes)

    # Diferencias entre cada padrón
    st.subheader("🧩 Diferencias entre padrones")
    for i, d in enumerate(padrones_con_dni):
        faltan = comunes[~comunes["dni"].isin(d["dni"])]
        st.write(f"➡️ Faltan en padrón {i+1}: {len(faltan)}")
        st.dataframe(faltan)

# ---------------------------------------------------
# BUSQUEDA
# ---------------------------------------------------
st.header("🔎 Búsqueda")
q = st.text_input("Buscar por DNI, apellido, nombre o mail")

if q:
    ql = q.lower()
    res = df[
        df.apply(lambda r: ql in f"{r['dni']} {r['apellido'].lower()} {r['nombre'].lower()} {str(r['mail']).lower()}", axis=1)
    ]
    st.write(f"Resultados: {len(res)}")
    st.dataframe(res)

# ---------------------------------------------------
# DUPLICADOS
# ---------------------------------------------------
st.header("⚠️ Duplicados por DNI")
dup = df[df.duplicated("dni", keep=False) & df["dni"].astype(bool)]
if not dup.empty:
    st.warning(f"{dup['dni'].nunique()} DNIs duplicados - {len(dup)} filas")
    st.dataframe(dup)
else:
    st.success("Sin duplicados")

# ---------------------------------------------------
# GRAFICOS
# ---------------------------------------------------
st.header("📊 Gráficos avanzados")

st.subheader("Top 20 apellidos")
top_ap = df["apellido"].value_counts().head(20)
fig, ax = plt.subplots(figsize=(10,5))
ax.barh(top_ap.index, top_ap.values, color="#c8102e")
ax.invert_yaxis()
st.pyplot(fig)

st.subheader("Nombres más comunes (Top 10)")
top_n = df["nombre"].value_counts().head(10)
fig2, ax2 = plt.subplots(figsize=(6,6))
ax2.pie(top_n.values, labels=top_n.index, autopct="%1.1f%%")
ax2.axis("equal")
st.pyplot(fig2)

# ---------------------------------------------------
# EXPORTAR
# ---------------------------------------------------
st.header("📥 Exportar padrón unificado")
out = BytesIO()
df.to_excel(out, index=False, engine="openpyxl")
out.seek(0)

st.download_button(
    "Descargar Excel unificado",
    data=out,
    file_name="padron_unificado_unidad_roja_y_blanca.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

