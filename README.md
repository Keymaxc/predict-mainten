# Predictive Maintenance Mesin Pabrik

Pipeline data end-to-end untuk memprediksi kerusakan mesin pabrik: database PostgreSQL (Supabase), generator data sintetis dengan Python, analisis SQL, machine learning, dan dashboard.


## Pertanyaan bisnis

1. Mesin dan komponen mana yang paling sering rusak, dan berapa biaya serta downtime-nya?
2. Apakah perawatan preventif benar-benar menurunkan kerusakan?
3. Bisakah kerusakan diprediksi beberapa hari sebelum terjadi dari pola sensor?

## Arsitektur

```
generate_data.py (Python)  ->  CSV  ->  load_to_supabase.py (COPY)  ->  PostgreSQL (Supabase)
                                                                              |
                                              SQL (cleaning & analisis) <-----+----> Python / ML
                                                                              |
                                                                  Power BI & Tableau (dashboard)
```

## Struktur repo

```
.
├── README.md
├── requirements.txt
├── .env.example          # contoh konfigurasi (isi asli di .env, tidak di-upload)
├── .gitignore
├── scripts/
│   ├── generate_data.py      # membuat data sintetis -> data/raw/*.csv
│   └── load_to_supabase.py   # memuat CSV ke database
├── sql/
│   ├── 01_schema.sql                 # 5 tabel, relasi, validasi, index, RLS
│   └── 02_sample_and_practice.sql    # data contoh + latihan INSERT/UPDATE/DELETE/JOIN
└── data/raw/                 # hasil generate (file sensor besar tidak di-upload)
```

## Skema database

| Tabel | Satu baris mewakili | Isi utama |
|---|---|---|
| `machines` | satu mesin | tipe, model, jalur produksi, tanggal pasang, status |
| `sensor_readings` | satu pembacaan sensor | voltase, rpm, tekanan, getaran, suhu |
| `maintenance_logs` | satu perawatan | komponen, tipe (preventive/corrective), biaya (Rp), downtime |
| `failures` | satu kerusakan | komponen, jenis, severity, downtime (label untuk ML) |
| `error_logs` | satu error ringan | kode error, deskripsi, severity (sinyal dini) |

Semua tabel anak terhubung ke `machines` lewat `machine_id`. Validasi (CHECK, UNIQUE, FOREIGN KEY) dijaga di level database.

## Data sintetis

Data dibuat oleh `scripts/generate_data.py` (seed tetap, jadi hasilnya bisa direproduksi): 40 mesin, pembacaan per jam Januari 2025 - Oktober 2026, sekitar 640 ribu baris sensor. Pola yang sengaja ditanam:

- sensor memburuk bertahap 2-5 hari sebelum rusak, dengan tanda berbeda tiap komponen
- error ringan makin sering menjelang kerusakan, ditambah alarm palsu acak
- mesin lebih tua dan model tertentu lebih sering rusak
- perawatan preventif menurunkan peluang komponen yang sama rusak dalam 90 hari berikutnya
- tidak ada pembacaan saat mesin mati; ada sedikit nilai kosong dan lonjakan palsu untuk latihan cleaning

Struktur tabel mengacu pada dataset publik *Microsoft Azure Predictive Maintenance* (Kaggle) dengan penambahan kolom suhu, biaya perawatan, downtime, dan severity. Seluruh data di repo ini sintetis.

## Cara menjalankan

1. Buat project di [Supabase](https://supabase.com), lalu jalankan `sql/01_schema.sql` di SQL Editor.
2. Salin string koneksi **Session pooler** (tombol Connect), lalu buat file `.env` dari `.env.example`.
3. Install dependensi dan jalankan:

```bash
pip install -r requirements.txt
python scripts/generate_data.py
python scripts/load_to_supabase.py          # tambahkan --reset untuk mengulang dari nol
```

Bisa juga dijalankan di Google Colab: simpan `DATABASE_URL` di Colab Secrets, lalu clone repo ini dan jalankan dua script yang sama.

## Roadmap

- [x] Skema database (PostgreSQL / Supabase)
- [x] Generator data sintetis
- [x] Loader ke database
- [ ] Data cleaning dan analisis dengan SQL
- [ ] Eksplorasi di Excel
- [ ] Model ML prediksi kerusakan (Python)
- [ ] Dashboard Power BI
- [ ] Dashboard Tableau

## Referensi

- Microsoft Azure Predictive Maintenance (Kaggle)
- AI4I 2020 Predictive Maintenance Dataset, S. Matzka (CC-BY-NC-SA-4.0)
