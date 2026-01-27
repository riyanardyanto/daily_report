
# Daily Report App

Aplikasi untuk membuat dan melihat laporan harian berbasis Python. Proyek ini membaca data target/riwayat, menampilkan metrik dan tabel (history/metrics/stops/target), serta menyediakan halaman/response berbasis HTML untuk kebutuhan tampilan tertentu.

Struktur proyek mengarah ke aplikasi UI di folder `src/` dengan komponen dan service terpisah agar mudah dirawat.

## Fitur Utama

- Menampilkan ringkasan metrik dan tabel data (history/metrics/stops/targets).
- Manajemen target dari file CSV di `data_app/targets/`.
- Penyimpanan riwayat di `data_app/history/history.db` (SQLite).
- Pengaturan aplikasi via `data_app/settings/config.toml`.

## Prasyarat

- Python 3.10+ (disarankan 3.11/3.12)
- Windows PowerShell (sudah sesuai dengan workspace ini)

## Instalasi

1. Masuk ke folder proyek:

	```powershell
	cd D:\Program\Python\daily_report
	```

2. (Opsional tapi disarankan) Buat virtual environment:

	```powershell
	python -m venv .venv
	.\.venv\Scripts\Activate.ps1
	```

3. Install dependencies.

	Jika proyek memakai Poetry (ada `pyproject.toml`), jalankan:

	```powershell
	pip install poetry
	poetry install
	poetry run python main.py
	```

	Jika tidak memakai Poetry, Anda bisa coba:

	```powershell
	pip install -e .
	```

	Catatan: Cara install yang tepat mengikuti pengaturan di `pyproject.toml`.

## Konfigurasi

File konfigurasi ada di:

- `data_app/settings/config.toml` — pengaturan utama aplikasi.
- `data_app/settings/user.txt` — data user (misalnya nama/operator) yang ditampilkan di laporan.
- `data_app/settings/link_up.txt` — link/URL atau referensi yang dibutuhkan aplikasi.

Pastikan file-file tersebut ada dan terisi sesuai kebutuhan lingkungan Anda.

Data yang dipakai aplikasi:

- `data_app/history/history.db` — data riwayat (SQLite).
- `data_app/history/history.csv` — sumber migrasi/backup lama (opsional) dan target export.
- `data_app/targets/*.csv` — file target (contoh: `target_make_21.csv`, `target_pack_24.csv`).

### Pengaturan Performa UI

Beberapa optimasi performa bisa di-tuning dari bagian `[UI]` di `data_app/settings/config.toml`:

- `history_max_rows`: membatasi jumlah baris history yang dirender di dialog History (lebih kecil = lebih cepat).
- `qr_cache_size`: jumlah payload QR yang di-cache di memori untuk mempercepat open QR berulang.
- `spa_cache_ttl_seconds`: TTL (detik) cache hasil tombol **Get Data** untuk input yang sama. Set `0` untuk mematikan cache.

## Optimasi Performa & Stabilitas UI

Perubahan berikut sudah diterapkan untuk meningkatkan responsivitas dan mencegah UI “hang”:

- **Dialog lebih stabil**: pembukaan dialog dibuat lebih robust (fallback page resolution + helper pembuka dialog) sehingga tidak “silent fail”.
- **QR Code lebih responsif**: dialog QR tampil cepat dengan state loading, proses generate dipindah ke background, dan hasilnya di-cache.
- **History lebih cepat dibuka**: dialog History tampil cepat dengan loading, baca SQLite dipindah ke background, plus limit render via `history_max_rows`.
- **Get Data non-blocking**: fetch/parse/proses SPA dipindah ke background sehingga UI tetap responsif.
- **Anti stale-result**: hasil task lama tidak menimpa hasil terbaru saat user klik Get Data berkali-kali.
- **Indikator status**: status bar menampilkan `Loading…` saat proses, dan `(...Cached)` saat hasil berasal dari cache.

## Cara Menjalankan

Jalankan aplikasi dengan salah satu cara berikut:

### Opsi A (disarankan): Jalankan via `uv`

```powershell
uv run main.py
```

### Opsi B: Jalankan via `main.py`

```powershell
python main.py
```

### Opsi C: Jalankan modul app (jika dipakai sebagai entrypoint)

```powershell
python -m src
```

Jika Anda memakai Poetry:

```powershell
poetry run python main.py
```

## Compile / Build menjadi EXE (Windows)

Pastikan `uv` dan `pyinstaller` tersedia di environment Python Anda.

Karena aplikasi ini memakai Flet Desktop, binary client-nya (`flet.exe` + DLL) harus ikut dibundle. Jika tidak, saat EXE dijalankan Flet akan mencoba download client dari internet dan bisa gagal (contoh error `getaddrinfo failed`).

### Opsi A (disarankan): build pakai spec

```powershell
uv run pyinstaller --clean "Daily Report.spec"
```

### Opsi B: build langsung dari `main.py` (manual)

```powershell
uv run pyinstaller --clean --onefile --windowed --name "Daily Report" --icon "src\assets\icon_windows.ico" --add-data "src\assets;src\assets" --collect-all flet_desktop main.py
```

Hasil build biasanya ada di folder `dist/` dengan nama `Daily Report.exe`.

## Cara Penggunaan (Alur Umum)

1. Pastikan konfigurasi sudah benar (lihat bagian **Konfigurasi**).
2. Jalankan aplikasi.
3. Gunakan sidebar untuk berpindah tampilan:
	- Laporan/daftar report
	- Tabel history
	- Tabel metrik
	- Tabel stops
	- Editor target
4. Jika perlu memperbarui target, edit file CSV di `data_app/targets/` atau melalui fitur editor target (jika tersedia di UI), lalu refresh tampilan.
5. Riwayat akan tersimpan/terbaca dari `data_app/history/history.db` (SQLite). CSV dipakai untuk migrasi/import/export.

## Import history.csv ke history.db

Jika Anda punya file `history.csv` (misalnya dari komputer lain) dan ingin menambahkan datanya ke `history.db`, ada 2 cara:

Saat ini fitur **Load from CSV** dan script CLI helper untuk import CSV sudah dihapus (tidak dipakai lagi).

Jika Anda butuh menggabungkan history antar komputer, gunakan mekanisme sync yang ada (History dialog akan melakukan sync), atau beritahu saya jika ingin saya buatkan kembali helper import CSV yang sederhana.



## Struktur Folder Penting

- `main.py` — entrypoint aplikasi.
- `src/app.py` — implementasi aplikasi UI.
- `src/components/` — komponen UI (tabel, dialog, sidebar, dll).
- `src/services/` — service untuk config/history/SPA.
- `src/utils/` — helper util.
- `data_app/` — data & konfigurasi runtime (history, log, settings, targets).

## Troubleshooting

- **Aplikasi gagal start / module not found**: pastikan dependencies ter-install (lihat **Instalasi**) dan Anda menjalankan dari folder proyek.
- **Data tidak muncul**: cek apakah `data_app/history/history.db` ada dan file target di `data_app/targets/` tersedia.
	Jika Anda masih punya `data_app/history/history.csv` (atau file CSV lain), lakukan import ke DB (lihat bagian **Import history.csv ke history.db**).
- **Konfigurasi tidak terbaca**: pastikan `data_app/settings/config.toml` ada dan tidak kosong.
- **Muncul warning GIL (Python 3.14 free-threaded)**: warning ini biasanya tidak menghentikan aplikasi. Jika ingin minim warning/lebih stabil, gunakan Python 3.11/3.12 sesuai rekomendasi di **Prasyarat**.


