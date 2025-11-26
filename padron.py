# app.py - Sistema Integral de Militancia (FINAL + Multi Cruce)
import streamlit as st
import pandas as pd
import pdfplumber
from pdf2image import convert_from_bytes
import pytesseract
import re
from io import BytesIO, StringIO
from fpdf import FPDF
import matplotlib.pyplot as plt
import seaborn as sns
import warnings

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Unidad Roja y Blanca - Padrón", layout="wide")
DEFAULT_LIST_NAME = "unidad roja y blanca"

# ---------------------------------------------------------------------
# PARSEADOR DE LÍNEAS DE PDF
# ---------------------------------------------------------------------
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
    elif len(tokens) == 2:
        apellido = tokens[0]
        nombre = tokens[1]
    else:
        apellido = tokens[0] if tokens else ""
        nombre = ""

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
    return pd.DataFrame(rows) if rows else pd.DataFrame()

# ---------------------------------------------------------------------
# EXTRACCIÓN DE TEXTO
# ---------------------------------------------------------------------
def extract_text_with_pdfplumber(raw):
    txt = ""
    try:
        with pdfplumber.open(BytesIO(raw)) as pdf:
            for p in pdf.pages:
                t = p.extract_text()
                if t:
                    txt += t + "\n"
    except:
        pass
    return txt

def extract_text_with_ocr(raw):
    txt = ""
    try:
        imgs = convert_from_bytes(raw, dpi=250)
        for img in imgs:
            txt += pytesseract.image_to_string(img, lang="spa") + "\n"
    except:
        pass
    return txt

# ---------------------------------------------------------------------
# NORMALIZACIÓN DE EXCEL/CSV
# ---------------------------------------------------------------------
def normalize_excel_df(df):
    out = pd.DataFrame()
    out["n"] = df.index.astype(str)

    col_dni = next((c for c in df.columns if "dni" in c.lower()), None)
    out["dni"] = df[col_dni].astype(str).str.replace(r"\D", "", regex=True).str.strip() if col_dni else ""

    col_ap = next((c for c in df.columns if "apell" in c.lower()), None)
    col_no = next((c for c in df.columns if "nom" in c.lower()), None)
    out["apellido"] = df[col_ap].astype(str).str.title().str.strip() if col_ap else ""
    out["nombre"] = df[col_no].astype(str).str.title().str.strip() if col_no else ""

    col_mail = next((c for c in df.columns if "mail" in c.lower() or
                     "email" in c.lower() or
                     "domicilio" in c.lower() or
                     "direc" in c.lower()), None)
    out["mail"] = df[col_mail].astype(str).str.strip() if col_mail else ""

    col_ing = next((c for c in df.columns if any(x in c.lower() for x in
                                                 ["ingreso","fecha","alta","inscrip"])), None)

    out["fecha_ingreso"] = pd.to_datetime(df[col_ing], errors="coerce") if col_ing else pd.NaT

    return out

# ---------------------------------------------------------------------
# LECTURA GENERAL
# ---------------------------------------------------------------------
def load_file_to_df(file):
    name = file.name.lower()
    raw = file.read()

    if name.endswith(".pdf"):
        text = extract_text_with_pdfplumber(raw)
        df = parse_text_block_to_df(text)
        if df.empty:
            st.info("Aplicando OCR (tarda unos segundos)...")
            text = extract_text_with_ocr(raw)
            df = parse_text_block_to_df(text)
        df["mail"] = ""
        df["fecha_ingreso"] = pd.NaT
        return df

    if name.endswith((".xlsx", ".xls")):
        return normalize_excel_df(pd.read_excel(BytesIO(raw), engine="openpyxl"))

    if name.endswith(".csv"):
        try:
            df_csv = pd.read_csv(StringIO(raw.decode("utf-8")))
        except:
            df_csv = pd.read_csv(StringIO(raw.decode("latin1")))
        return normalize_excel_df(df_csv)

    return pd.DataFrame()

# ---------------------------------------------------------------------
# UI PRINCIPAL
# ---------------------------------------------------------------------
st.title("📋 Sistema Integral de Militancia – Unidad Roja y Blanca")
st.write("Subí un Padrón y automáticamente procesamos DNI, Apellido, Nombre, Mail y Fecha de Ingreso.")

uploaded = st.file_uploader("Subir padrón principal", type=["pdf","xlsx","xls","csv"])

if not uploaded:
    st.stop()

df = load_file_to_df(uploaded)

if df.empty:
    st.error("No se pudo leer el archivo")
    st.stop()

# Normalización final
df["dni"] = df["dni"].astype(str).str.replace(r"\D", "", regex=True)
df["apellido"] = df["apellido"].astype(str).str.title()
df["nombre"] = df["nombre"].astype(str).str.title()
df["mail"] = df["mail"].astype(str).str.strip()

st.subheader("Vista previa")
st.dataframe(df.head(200), use_container_width=True)

# BUSCADOR
st.subheader("🔎 Buscar socio")
q = st.text_input("Buscar por DNI / Apellido / Nombre / Mail")

if q:
    ql = q.lower()
    mask = df.apply(lambda r: ql in (
        str(r["dni"]) + " " +
        str(r["apellido"]).lower() + " " +
        str(r["nombre"]).lower() + " " +
        str(r["mail"]).lower()
    ), axis=1)
    st.dataframe(df[mask], use_container_width=True)

# DUPLICADOS
st.subheader("⚠️ Duplicados por DNI")
dup = df[df.duplicated("dni", keep=False) & df["dni"].astype(bool)]
if len(dup):
    st.warning(f"{len(dup)} filas duplicadas | {dup['dni'].nunique()} DNIs")
    st.dataframe(dup)
else:
    st.success("Sin duplicados 👍")

# MÉTRICAS
st.header("📊 Métricas")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total", len(df))
c2.metric("Con mail", df["mail"].astype(bool).sum())
c3.metric("Con fecha ingreso", df["fecha_ingreso"].notna().sum())
c4.metric("Duplicados", dup["dni"].nunique())

# GRÁFICOS
st.header("📈 Gráficos Avanzados")

# Top apellidos
top_ap = df["apellido"].value_counts().head(20)
fig, ax = plt.subplots(figsize=(10,6))
ax.barh(top_ap.index, top_ap.values, color="#c8102e")
ax.invert_yaxis()
st.pyplot(fig)

# Nombres pie
top_n = df["nombre"].value_counts().head(10)
fig2, ax2 = plt.subplots(figsize=(6,6))
ax2.pie(top_n.values, labels=top_n.index, autopct="%1.1f%%")
st.pyplot(fig2)

# Boxplot DNI
numeric_dni = pd.to_numeric(df["dni"], errors="coerce").dropna()
fig3, ax3 = plt.subplots(figsize=(10,3))
ax3.boxplot(numeric_dni, vert=False)
st.pyplot(fig3)

# Heatmap iniciales
df["ini_ap"] = df["apellido"].str[:1].str.upper()
df["ini_no"] = df["nombre"].str[:1].str.upper()
ct = pd.crosstab(df["ini_ap"], df["ini_no"])
fig4, ax4 = plt.subplots(figsize=(10,6))
sns.heatmap(ct, cmap="Reds")
st.pyplot(fig4)

# EXPORT EXCEL
buf = BytesIO()
df.to_excel(buf, index=False, engine="openpyxl")
buf.seek(0)
st.download_button("📥 Descargar Excel Procesado", buf,
    "padron_unidad_roja_y_blanca.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# ---------------------------------------------------------------------
# 🔥 ***CRUCE MÚLTIPLE DE PADRONES*** (N archivos)
# ---------------------------------------------------------------------
st.header("🔗 Cruce de múltiples padrones (2, 3, 5, 10 o más)")

multi_files = st.file_uploader(
    "Subir varios padrones para cruzarlos entre sí",
    type=["pdf","xlsx","xls","csv"],
    accept_multiple_files=True
)

if multi_files:
    st.info(f"Archivos subidos: {len(multi_files)}")

    dfs = []
    for f in multi_files:
        d = load_file_to_df(f)
        if not d.empty:
            d["source"] = f.name
            dfs.append(d)

    if not dfs:
        st.error("Ningún archivo válido.")
        st.stop()

    bigdf = pd.concat(dfs, ignore_index=True)

    # Normalizar
    bigdf["dni"] = bigdf["dni"].astype(str).str.replace(r"\D","",regex=True)
    bigdf["mail"] = bigdf["mail"].astype(str).str.lower().str.strip()

    # Coincidencias por DNI
    st.subheader("📌 Coincidencias por DNI")
    dup_all = bigdf[bigdf.duplicated("dni", keep=False) & bigdf["dni"].astype(bool)]
    st.dataframe(dup_all)

    # Coincidencias por mail
    st.subheader("📌 Coincidencias por MAIL")
    mail_dup = bigdf[bigdf.duplicated("mail", keep=False) & bigdf["mail"].astype(bool)]
    st.dataframe(mail_dup)

    # Conteo por archivo
    st.subheader("📌 Cantidad de coincidencias por archivo")
    cross_counts = dup_all.groupby("source")["dni"].count()
    st.bar_chart(cross_counts)

    # Exportar cruce
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        dup_all.to_excel(writer, sheet_name="coincidencias_dni", index=False)
        mail_dup.to_excel(writer, sheet_name="coincidencias_mail", index=False)
        bigdf.to_excel(writer, sheet_name="todos_limpios", index=False)

    out.seek(0)
    st.download_button(
        "📥 Descargar informe de cruces",
        out,
        "cruce_padrones.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

st.success("Listo rey 💪🔥 — Tu sistema está completo, procesando PDFs, Excel, mails y cruzando padrones sin límites.")
