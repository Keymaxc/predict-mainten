import argparse
import os
import sys
from pathlib import Path

import psycopg

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:          
    pass

DATA_DIR = Path("data/raw")
BATCH_LINES = 100_000        

TABLES = [
    ("machines", ["machine_id", "machine_name", "machine_type", "machine_model",
                  "production_line", "install_date", "status"]),
    ("sensor_readings", ["machine_id", "reading_time", "voltage", "rotation_rpm",
                         "pressure", "vibration", "temperature"]),
    ("maintenance_logs", ["machine_id", "maintenance_date", "component", "maintenance_type",
                          "cost_idr", "downtime_hours"]),
    ("failures", ["machine_id", "failure_time", "component", "failure_type",
                  "severity", "downtime_hours"]),
    ("error_logs", ["machine_id", "error_time", "error_code", "error_description", "severity"]),
]
IDENTITY_FIX = [("machines", "machine_id")]


def copy_csv(cur, table: str, cols: list[str], path: Path) -> int:
    """Muat satu CSV ke tabel dengan COPY, per batch."""
    sql = f"COPY {table} ({', '.join(cols)}) FROM STDIN WITH (FORMAT csv, HEADER false)"
    total = 0
    with open(path, "rb") as f:
        header = f.readline().decode().strip().split(",")
        if header != cols:
            sys.exit(f"Kolom {path.name} tidak cocok.\n  CSV    : {header}\n  Diharap: {cols}")
        while True:
            lines = [ln for _, ln in zip(range(BATCH_LINES), f)]
            if not lines:
                break
            with cur.copy(sql) as cp:
                cp.write(b"".join(lines))
            total += len(lines)
            print(f"    {table}: {total:,} baris...", end="\r", flush=True)
    print(f"    {table}: {total:,} baris selesai.        ")
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="kosongkan semua tabel sebelum memuat")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL belum diatur. Lihat petunjuk di bagian atas file ini.")

    missing = [t for t, _ in TABLES if not (DATA_DIR / f"{t}.csv").exists()]
    if missing:
        sys.exit(f"File CSV tidak ditemukan: {missing}. Jalankan generate_data.py dulu.")

    try:
        conn = psycopg.connect(url, connect_timeout=15)
    except psycopg.OperationalError as e:
        sys.exit(
            "Gagal terhubung ke database.\n"
            "  - Pastikan memakai string 'Session pooler' dari tombol Connect di Supabase.\n"
            "    String 'Direct connection' memakai IPv6 dan sering gagal di jaringan IPv4.\n"
            "  - Cek password (karakter khusus harus di-URL-encode) dan bahwa project tidak sedang di-pause.\n"
            f"  Detail: {e}"
        )

    with conn, conn.cursor() as cur:
        cur.execute("set statement_timeout = 0")

        if args.reset:
            names = ", ".join(t for t, _ in TABLES)
            cur.execute(f"truncate {names} restart identity cascade")
            print("Semua tabel dikosongkan.")
        else:
            for t, _ in TABLES:
                cur.execute(f"select count(*) from {t}")
                if cur.fetchone()[0] > 0:
                    sys.exit(f"Tabel {t} sudah berisi data. Jalankan dengan --reset jika ingin mengulang.")

        for table, cols in TABLES:
            print(f"Memuat {table} ...")
            copy_csv(cur, table, cols, DATA_DIR / f"{table}.csv")
        for table, col in IDENTITY_FIX:
            cur.execute(
                f"select setval(pg_get_serial_sequence('{table}', '{col}'), "
                f"(select coalesce(max({col}), 1) from {table}))"
            )

        print("\nRingkasan isi database:")
        for table, _ in TABLES:
            cur.execute(f"select count(*) from {table}")
            print(f"  {table:<18}: {cur.fetchone()[0]:>9,} baris")
        cur.execute("select pg_size_pretty(pg_database_size(current_database()))")
        print(f"\nUkuran database sekarang: {cur.fetchone()[0]} (batas paket gratis: 500 MB)")

    print("Selesai. Data berhasil dimuat.")


if __name__ == "__main__":
    main()
