import streamlit as st
from supabase import create_client, Client as SupabaseClient
import pandas as pd
from openrouter import OpenRouter # Kembali ke import asli
import matplotlib.pyplot as plt
import seaborn as sns

# =======================================================================
# 1. KONEKSI & SETUP (Menggunakan Streamlit Secrets)
# =======================================================================

# Ambil kunci dari file secrets.toml
try:
    SUPABASE_URL = st.secrets["https://yrlqlzvhtyyzlcasviij.supabase.co"]
    SUPABASE_KEY = st.secrets["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlybHFsenZodHl5emxjYXN2aWlqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1NTIwNDcsImV4cCI6MjA3NzEyODA0N30.a2zQkdOQYVt-EFnCt-jd20ygwn2048lb-Mtgpe-t4uw"]
    OPENROUTER_KEY = st.secrets["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"]
except KeyError as e:
    st.error(f"Error: Kunci '{e}' tidak ditemukan di file .streamlit/secrets.toml. Pastikan file ada dan nama kunci benar (huruf besar).")
    st.stop()
except FileNotFoundError:
    st.error("Error: File .streamlit/secrets.toml tidak ditemukan. Pastikan file ada di folder .streamlit di dalam folder proyek Anda.")
    st.stop()

# Buat koneksi ke Supabase
try:
    supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Gagal terhubung ke Supabase: {e}")
    st.stop()

# Buat koneksi ke AI
client_ai = None # Default ke None
try:
    client_ai = OpenRouter(api_key=OPENROUTER_KEY)
except NameError:
    st.warning("Library 'OpenRouter' tidak bisa diimpor. Fitur AI tidak akan aktif.")
except Exception as e:
    st.warning(f"Gagal terhubung ke OpenRouter: {e}. Fitur AI tidak akan aktif.")


# =======================================================================
# 2. JUDUL APLIKASI
# =======================================================================
st.set_page_config(layout="wide")
st.title("🚀 Talent Match Intelligence System")
st.write("Aplikasi ini membantu menemukan talenta internal yang cocok dengan profil benchmark.")

# =======================================================================
# 3. FUNGSI AMBIL DAFTAR KARYAWAN
# =======================================================================
@st.cache_data(ttl=3600) # Cache selama 1 jam
def get_employee_list():
    try:
        response = supabase.table('employees').select('employee_id, fullname').execute()
        if response.data:
             # Sort dictionary by employee name (value)
            sorted_employees = sorted(response.data, key=lambda x: x['fullname'])
            return {emp['employee_id']: emp['fullname'] for emp in sorted_employees}
        return {}
    except Exception as e:
        st.error(f"Error mengambil daftar karyawan: {e}")
        return {}

employee_dict = get_employee_list()
if not employee_dict:
    st.error("Gagal memuat daftar karyawan dari database. Periksa koneksi/nama tabel.")
    st.stop()

# =======================================================================
# 4. FORM INPUT
# =======================================================================
with st.form(key="benchmark_form"):
    st.header("1. Role Information")
    role_name_input = st.text_input("Role Name", placeholder="Ex. Data Analyst")
    job_level_input = st.selectbox("Job Level", ["Staff", "Supervisor", "Manager", "Senior Manager"])
    role_purpose_input = st.text_area("Role Purpose", placeholder="1-2 sentences describe role outcome...")

    st.header("2. Employee Benchmarking")
    employee_names_options = list(employee_dict.values())
    selected_benchmark_names = st.multiselect(
        "Select Employee Benchmarking (min 1, max 3)",
        options=employee_names_options,
        max_selections=3
    )

    submit_button = st.form_submit_button("✨ Generate Profile & Find Matches")

# =======================================================================
# 5. LOGIKA SETELAH SUBMIT
# =======================================================================
if submit_button:
    # --- VALIDASI INPUT ---
    if not role_name_input or not job_level_input or not role_purpose_input or not selected_benchmark_names:
        st.error("❌ Semua field wajib diisi!")
    elif len(selected_benchmark_names) < 1:
        st.error("❌ Pilih minimal 1 karyawan benchmark!")
    else:
        st.info("🔄 Memproses permintaan Anda...")
        with st.spinner("Menyimpan benchmark, memanggil AI, dan menghitung skor..."):

            # --- LANGKAH 5.1: SIMPAN BENCHMARK ---
            name_to_id_dict = {v: k for k, v in employee_dict.items()}
            selected_benchmark_ids = [name_to_id_dict[name] for name in selected_benchmark_names]
            insert_success = False
            try:
                insert_response = supabase.table('talent_benchmarks').insert({
                    "role_name": role_name_input,
                    "job_level": job_level_input,
                    "role_purpose": role_purpose_input,
                    "selected_talent_ids": selected_benchmark_ids
                }).execute()
                # Periksa apakah ada data yang dikembalikan (indikasi sukses)
                if hasattr(insert_response, 'data') and insert_response.data:
                    insert_success = True
                else:
                    error_detail = insert_response.error.message if hasattr(insert_response, 'error') and insert_response.error else "No data returned after insert"
                    st.error(f"Gagal menyimpan data benchmark: {error_detail}")
                    st.stop()
            except Exception as e:
                st.error(f"Error menyimpan benchmark ke Supabase: {e}")
                st.stop()

            # --- LANGKAH 5.2: PANGGIL AI ---
            ai_output = None
            if client_ai: # Hanya jalankan jika client_ai berhasil dibuat
                st.subheader("🤖 AI-Generated Job Profile")
                try:
                    prompt = f"""
                    Buatkan draf profil pekerjaan ringkas untuk posisi: {role_name_input} ({job_level_input}).
                    Tujuan utama peran ini: {role_purpose_input}.
                    Profil kandidat ideal (berdasarkan benchmark): Sangat empatik & komunikatif (Social Intelligence); Disiplin & fokus kualitas (Discipline); Berorientasi masa depan & proaktif (Vision).
                    Buatkan hanya 3 bagian: Job Description (1 paragraf), Key Responsibilities (3-5 poin), Key Competencies (3-5 poin). Gunakan Bahasa Indonesia.
                    """
                    response_ai = client_ai.chat.completions.create(
                        model="mistralai/mistral-7b-instruct:free",
                        messages=[{"role": "user", "content": prompt}], max_tokens=400
                    )
                    ai_output = response_ai.choices[0].message.content
                except Exception as e:
                    st.warning(f"Gagal memanggil AI: {e}. Lanjut tanpa profil AI.")
            else:
                 st.warning("Koneksi ke AI (OpenRouter) tidak disiapkan. Profil AI dilewati.")

            if ai_output:
                st.markdown(ai_output)
            st.markdown("---") # Garis pemisah

            # --- LANGKAH 5.3: JALANKAN KUERI SQL ---
            st.header("📊 Ranked Talent List & Dashboard")
            df_results = None
            try:
                data_response = supabase.rpc('get_talent_match_results').execute()

                if not data_response.data:
                    error_detail = data_response.error.message if hasattr(data_response, 'error') and data_response.error else "No data returned from function"
                    st.error(f"Gagal menjalankan kueri SQL 'get_talent_match_results': {error_detail}")
                    st.write("Pastikan function ada di Supabase & benchmark sudah dipilih.")
                    st.stop()

                df_results = pd.DataFrame(data_response.data)

            except Exception as e:
                st.error(f"Error saat menjalankan/memproses kueri SQL: {e}")
                st.write("Pastikan function 'get_talent_match_results' ada dan tidak error di Supabase.")
                st.stop()

            # --- LANGKAH 5.4: TAMPILKAN OUTPUT ---
            if df_results is not None and not df_results.empty:
                st.subheader("🏆 Ranked Talent List (Top Matches)")
                df_ranked_list = df_results.drop_duplicates(subset=['employee_id']).sort_values(
                    by="final_match_rate", ascending=False, na_position='last'
                )
                
                # Periksa nama kolom 'position_name' (pengganti 'role')
                if 'position_name' not in df_ranked_list.columns:
                    st.error("Kolom 'position_name' tidak ditemukan dalam hasil kueri. Periksa function SQL.")
                    st.write("Kolom yang tersedia:", df_ranked_list.columns.tolist())
                    st.stop()

                st.dataframe(
                    df_ranked_list[['fullname', 'position_name', 'directorate', 'grade', 'final_match_rate']].head(20),
                    use_container_width=True, hide_index=True,
                    column_config={"final_match_rate": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)}
                )

                st.subheader("💡 Dashboard Visualizations")
                col1, col2 = st.columns(2)

                with col1:
                    st.write("**Distribusi Final Match Rate**")
                    fig1, ax1 = plt.subplots(figsize=(6, 4)) # Ukuran lebih kecil
                    sns.histplot(df_ranked_list['final_match_rate'].dropna(), kde=True, ax=ax1, bins=15, color='skyblue')
                    ax1.set_xlabel('Final Match Rate (%)', fontsize=10)
                    ax1.set_ylabel('Jumlah Karyawan', fontsize=10)
                    ax1.tick_params(axis='both', which='major', labelsize=8)
                    st.pyplot(fig1)

                with col2:
                    st.write("**Kekuatan TGV (Rata-rata Top 10)**")
                    top_10_ids = df_ranked_list.head(10)['employee_id']
                    df_top_10 = df_results[df_results['employee_id'].isin(top_10_ids)]
                    # Periksa apakah df_top_10 tidak kosong sebelum groupby
                    if not df_top_10.empty:
                        tgv_avg = df_top_10.drop_duplicates(
                            subset=['employee_id', 'tgv_name']
                        ).groupby('tgv_name')['tgv_match_rate'].mean().reset_index().sort_values(
                            by='tgv_match_rate', ascending=False
                        )
                        fig2, ax2 = plt.subplots(figsize=(6, 4)) # Ukuran lebih kecil
                        sns.barplot(data=tgv_avg, x='tgv_match_rate', y='tgv_name', ax=ax2, palette='coolwarm', hue='tgv_name', dodge=False, legend=False) # Hue for color
                        ax2.set_xlabel('Rata-rata Match Rate (%)', fontsize=10)
                        ax2.set_ylabel('TGV', fontsize=10)
                        ax2.tick_params(axis='both', which='major', labelsize=8)
                        ax2.set_xlim(0, 100)
                        st.pyplot(fig2)
                    else:
                        st.write("Tidak cukup data untuk menampilkan chart TGV.")

                st.success("✅ Analisis Selesai!")
            else:
                st.warning("Tidak ada hasil yang bisa ditampilkan.")
