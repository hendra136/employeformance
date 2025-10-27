import streamlit as st
from supabase import create_client, Client
import pandas as pd
from openrouter import OpenRouter # Ini bisa di-import karena kita install 'openrouter-client'
import matplotlib.pyplot as plt
import seaborn as sns

# =======================================================================
# 1. KONEKSI & SETUP (Menggunakan Streamlit Secrets)
# =======================================================================

# Ambil kunci dari file secrets.toml
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
OPENROUTER_KEY = st.secrets["OPENROUTER_KEY"]

# Buat koneksi ke Supabase
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) 
except Exception as e:
    st.error(f"Gagal terhubung ke Supabase: {e}")
    st.stop()

# Buat koneksi ke AI
try:
    client_ai = OpenRouter(api_key=OPENROUTER_KEY) 
except Exception as e:
    st.error(f"Gagal terhubung ke OpenRouter: {e}")
    st.stop()

# =======================================================================
# 2. JUDUL APLIKASI
# =======================================================================
st.set_page_config(layout="wide")
st.title("🚀 Talent Match Intelligence System")
st.write("Aplikasi ini akan membantu Anda menemukan talenta internal yang paling cocok dengan profil 'Top Performer' (Benchmark) Anda.")

# =======================================================================
# 3. FUNGSI UNTUK MENGAMBIL DATA
# =======================================================================
# Kita butuh daftar karyawan untuk dipilih sebagai benchmark
@st.cache_data(ttl=600) # Simpan cache selama 10 menit
def get_employee_list():
    try:
        response = supabase.table('employees').select('employee_id, fullname').execute()
        if response.data:
            # Ubah data dari list-of-dict menjadi dict {id: nama}
            return {emp['employee_id']: emp['fullname'] for emp in response.data}
        return {}
    except Exception as e:
        st.error(f"Error mengambil daftar karyawan: {e}")
        return {}

# Ambil daftar karyawan
employee_dict = get_employee_list()
if not employee_dict:
    st.error("Gagal memuat daftar karyawan dari database. Periksa koneksi/nama tabel 'employees'.")
    st.stop()

# =======================================================================
# [cite_start]4. FORM INPUT (Sesuai dokumen [cite: 89-93])
# =======================================================================
with st.form(key="benchmark_form"):
    st.header("1. Role Information")
    role_name = st.text_input("Role Name", "Ex. Marketing Manager")
    job_level = st.selectbox("Job Level", ["Staff", "Supervisor", "Manager", "Senior Manager"])
    role_purpose = st.text_area("Role Purpose", "1-2 sentences to describe role outcome")
    
    st.header("2. Employee Benchmarking")
    # Ubah format {id: nama} menjadi [nama1, nama2] untuk multiselect
    employee_names = list(employee_dict.values())
    selected_names = st.multiselect("Select Employee Benchmarking (max 3)", options=employee_names)
    
    submit_button = st.form_submit_button("🚀 Generate Job Description & Find Talent")

# =======================================================================
# 5. LOGIKA SETELAH TOMBOL SUBMIT DITEKAN
# =======================================================================
if submit_button:
    if not role_name or not job_level or not role_purpose or not selected_names:
        st.error("❌ Harap isi semua field sebelum submit!")
    else:
        with st.spinner("Menganalisis... Mohon tunggu..."):
            
            # --- TAHAP 3.1: SIMPAN DATA BARU ---
            # Ubah [nama1, nama2] kembali menjadi [id1, id2]
            # Ini adalah dictionary terbalik {nama: id}
            name_to_id_dict = {v: k for k, v in employee_dict.items()}
            selected_ids = [name_to_id_dict[name] for name in selected_names]
            
            try:
                # Simpan input form ke tabel talent_benchmarks
                insert_response = supabase.table('talent_benchmarks').insert({
                    "role_name": role_name,
                    "job_level": job_level,
                    "role_purpose": role_purpose,
                    "selected_talent_ids": selected_ids
                }).execute()
                
                if not insert_response.data:
                    st.error(f"Gagal menyimpan data benchmark: {insert_response.error}")
                    st.stop() # Hentikan eksekusi jika gagal
            
            except Exception as e:
                st.error(f"Error saat insert data: {e}")
                st.stop()
            
            # [cite_start]--- TAHAP 3.2: PANGGIL AI (LLM) --- [cite: 116-117]
            st.header("Al-Generated Job Profile")
            try:
                prompt = f"""
                Buatkan draf profil pekerjaan untuk posisi: {role_name} ({job_level}).
                Tujuan utama peran ini adalah: {role_purpose}.
                Berdasarkan 'Success Formula' kami, kandidat ideal memiliki 3 TGV utama: 
                1. Social Intelligence (Sangat empatik, komunikator ulung).
                2. Discipline (Fokus pada kualitas dan kepatuhan).
                3. Vision (Futuristik dan seorang inisiator/aktivator).
                
                Tolong buatkan draf yang menarik untuk:
                1. Job Description (Deskripsi Pekerjaan)
                2. Key Responsibilities (Tanggung Jawab Utama)
                3. Key Competencies (Kompetensi Kunci) (gabungkan TGV di atas)
                """
                
                response_ai = client_ai.chat.completions.create(
                    model="mistralai/mistral-7b-instruct:free", # Model gratis & cepat
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500
                )
                
                ai_output = response_ai.choices[0].message.content
                st.markdown(ai_output) # Tampilkan output AI
                
            except Exception as e:
                st.warning(f"Gagal memanggil AI: {e}. Melanjutkan tanpa AI.")

            # --- TAHAP 3.3: JALANKAN KUERI SQL UTAMA ---
            st.header("Ranked Talent List & Dashboard")
            try:
                # Panggil "function" SQL yang kita buat di Tahap 2
                data_response = supabase.rpc('get_talent_match_results').execute()
                
                if data_response.data:
                    # Ubah data (list of dict) menjadi DataFrame Pandas
                    df_results = pd.DataFrame(data_response.data)
                    
                    # --- TAHAP 3.4.A: TAMPILKAN RANKED LIST ---
                    st.subheader("Ranked Talent List (Top Matches)")
                    # Kita butuh 1 baris per karyawan (buang "duplikat")
                    df_ranked_list = df_results.drop_duplicates(subset=['employee_id']).sort_values(
                        by="final_match_rate", ascending=False
                    )
                    st.dataframe(
                        df_ranked_list[['fullname', 'role', 'directorate', 'grade', 'final_match_rate']].head(20),
                        use_container_width=True
                    )

                    # --- TAHAP 3.4.B: TAMPILKAN VISUALISASI ---
                    st.subheader("Dashboard Visualizations")
                    col1, col2 = st.columns(2)
                    
                    # Visual 1: Distribusi Skor
                    with col1:
                        st.write("Distribusi Final Match Rate (Semua Karyawan)")
                        fig, ax = plt.subplots()
                        sns.histplot(df_ranked_list['final_match_rate'].dropna(), kde=True, ax=ax, bins=20)
                        ax.set_xlabel('Final Match Rate (%)')
                        ax.set_ylabel('Jumlah Karyawan')
                        st.pyplot(fig)
                    
                    # Visual 2: Rata-rata TGV Teratas
                    with col2:
                        st.write("Kekuatan TGV (Rata-rata Top 10 Kandidat)")
                        # Ambil top 10 karyawan
                        top_10_ids = df_ranked_list.head(10)['employee_id']
                        # Filter data detail HANYA untuk top 10
                        df_top_10_details = df_results[df_results['employee_id'].isin(top_10_ids)]
                        
                        # Hitung rata-rata TGV
                        tgv_avg = df_top_10_details.drop_duplicates(
                            subset=['employee_id', 'tgv_name']
                        ).groupby('tgv_name')['tgv_match_rate'].mean().reset_index().sort_values(
                            by='tgv_match_rate', ascending=False
                        )
                        
                        fig, ax = plt.subplots()
                        sns.barplot(data=tgv_avg, x='tgv_match_rate', y='tgv_name', ax=ax, palette='viridis')
                        ax.set_xlabel('Rata-rata Match Rate (%)')
                        ax.set_ylabel('Talent Group Variable (TGV)')
                        st.pyplot(fig)

                else:
                    st.error(f"Gagal menjalankan kueri SQL. Error: {data_response.error}")
                    st.write("Pastikan Anda sudah membuat function 'get_talent_match_results' di SQL Editor Supabase.")
            
            except Exception as e:
                st.error(f"Error saat menjalankan kueri SQL: {e}")
                st.write("Pastikan Anda sudah membuat function 'get_talent_match_results' di SQL Editor Supabase.")


