# app.py
import streamlit as st
import pandas as pd
import numpy as np
from supabase import create_client
import plotly.express as px
import seaborn as sns
import matplotlib.pyplot as plt

# -------------------------
# Config: ambil dari Streamlit secrets
# -------------------------
SUPABASE_URL = st.secrets["https://yrlqlzvhtyyzlcasviij.supabase.co"]
SUPABASE_KEY = st.secrets["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlybHFsenZodHl5emxjYXN2aWlqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1NTIwNDcsImV4cCI6MjA3NzEyODA0N30.a2zQkdOQYVt-EFnCt-jd20ygwn2048lb-Mtgpe-t4uw"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Talent Match Dashboard", layout="wide")
st.title("Talent Match Dashboard — Step 3")

# -------------------------
# Helper: load data (cached)
# -------------------------
@st.cache_data(ttl=300)
def load_final_view():
    # ambil seluruh view final_match_view
    res = supabase.table("final_match_view").select("*").execute()
    data = res.data
    if data is None:
        return pd.DataFrame()
    return pd.DataFrame(data)

df = load_final_view()

if df.empty:
    st.error("Data tidak ditemukan. Pastikan view final_match_view tersedia di Supabase dan secrets benar.")
    st.stop()

# -------------------------
# Data cleaning / small fixes
# -------------------------
# Convert numeric strings to numeric types if needed
num_cols = ['baseline_score','user_score','tv_match_rate','tgv_match_rate','final_match_rate']
for c in num_cols:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')

# Aggregate per employee: final summary
df_emp = df.groupby(['employee_id','fullname']).agg(
    final_match_rate=('final_match_rate','max'),  # final rate same across tgv maybe, use max/mean
    avg_user_score=('user_score','mean'),
    tgv_count=('tgv_name','nunique')
).reset_index().sort_values('final_match_rate', ascending=False)

# Sidebar controls
st.sidebar.header("Filter & Controls")
top_n = st.sidebar.slider("Tampilkan Top N", min_value=5, max_value=50, value=10, step=5)
search_name = st.sidebar.text_input("Cari nama (substring)")

# Main: Ranking table
st.subheader("Ranking Karyawan (Final Match Rate)")
if search_name:
    df_emp = df_emp[df_emp['fullname'].str.contains(search_name, case=False, na=False)]

st.dataframe(df_emp.head(top_n))

# Bar chart Top N
st.subheader(f"Top {top_n} by Final Match Rate")
top_df = df_emp.head(top_n)
fig = px.bar(top_df, x='fullname', y='final_match_rate',
             hover_data=['employee_id','avg_user_score','tgv_count'],
             labels={'final_match_rate':'Final Match Rate'},
             height=400)
fig.update_layout(xaxis_tickangle=-45)
st.plotly_chart(fig, use_container_width=True)

# Select employee for detail
st.sidebar.subheader("Detail Pegawai")
selected_emp = st.sidebar.selectbox("Pilih employee_id", options=df_emp['employee_id'].tolist())

# Detail: show per-TGV breakdown & radar by TV if available
emp_df = df[df['employee_id'] == selected_emp].copy()
if emp_df.empty:
    st.info("Tidak ada data detail untuk employee ini.")
else:
    st.subheader("Detail: " + emp_df['fullname'].iloc[0])
    st.markdown(f"- **Final Match Rate:** {emp_df['final_match_rate'].dropna().unique()}")
    st.markdown(f"- **Jumlah TGV terlibat:** {emp_df['tgv_name'].nunique()}")

    # show TGV match rates bar
    tgv_plot = emp_df[['tgv_name','tgv_match_rate']].drop_duplicates().dropna()
    if not tgv_plot.empty:
        fig2 = px.bar(tgv_plot, x='tgv_name', y='tgv_match_rate',
                      labels={'tgv_match_rate':'TGV Match Rate (%)'}, height=350)
        st.plotly_chart(fig2, use_container_width=True)

    # TV-level heatmap (pivot tv_name x tv_match_rate)
    pivot = emp_df.pivot_table(index='tv_name', values='tv_match_rate', aggfunc='max').reset_index()
    if not pivot.empty:
        st.subheader("TV Match Rates (per TV)")
        st.dataframe(pivot.sort_values('tv_match_rate', ascending=False))
        # small heatmap
        plt.figure(figsize=(6, max(1, len(pivot)/4)))
        sns.heatmap(pivot.set_index('tv_name').T, annot=True, cmap='YlGnBu', cbar=True)
        st.pyplot(plt.gcf())
        plt.clf()

    # Radar: take TV numeric scores (user_score) normalized
    tv_scores = emp_df.pivot_table(index='tv_name', values='user_score', aggfunc='max').dropna()
    if not tv_scores.empty:
        st.subheader("Radar: TV (user scores)")
        labels = tv_scores.index.tolist()
        values = tv_scores['user_score'].values.tolist()
        # normalize to 0-1
        vals = (np.array(values) - np.nanmin(values)) / (np.nanmax(values) - np.nanmin(values) + 1e-9)
        vals = np.concatenate([vals, [vals[0]]])
        angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False).tolist()
        angles += angles[:1]
        import matplotlib.pyplot as plt
        fig = plt.figure(figsize=(6,6))
        ax = fig.add_subplot(111, polar=True)
        ax.plot(angles, vals, linewidth=1, linestyle='solid')
        ax.fill(angles, vals, alpha=0.3)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, fontsize=8)
        st.pyplot(fig)
        plt.clf()

st.sidebar.markdown("---")
st.sidebar.markdown("Data source: Supabase `final_match_view`")
