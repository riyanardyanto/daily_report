
# Daily Report App

Aplikasi untuk membuat dan melihat laporan harian berbasis Python. Proyek ini membaca data target/riwayat, menampilkan metrik dan tabel (history/metrics/stops/target), serta menyediakan halaman/response berbasis HTML untuk kebutuhan tampilan tertentu.

Struktur proyek mengarah ke aplikasi UI di folder `src/` dengan komponen dan service terpisah agar mudah dirawat.

## Fitur Utama

- Menampilkan ringkasan metrik dan tabel data (history/metrics/stops/targets).
- Manajemen target dari file CSV di `data_app/targets/`.
- Penyimpanan riwayat di `data_app/history/history.csv`.
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

- `data_app/history/history.csv` — data riwayat.
- `data_app/targets/*.csv` — file target (contoh: `target_make_21.csv`, `target_pack_24.csv`).

## Cara Menjalankan

Jalankan aplikasi dengan salah satu cara berikut:

### Opsi A: Jalankan via `main.py`

```powershell
python main.py
```

### Opsi B: Jalankan modul app (jika dipakai sebagai entrypoint)

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
5. Riwayat akan tersimpan/terbaca dari `data_app/history/history.csv`.

## Struktur Folder Penting

- `main.py` — entrypoint aplikasi.
- `src/app.py` — implementasi aplikasi UI.
- `src/components/` — komponen UI (tabel, dialog, sidebar, dll).
- `src/services/` — service untuk config/history/SPA.
- `src/utils/` — helper util.
- `data_app/` — data & konfigurasi runtime (history, log, settings, targets).

## Troubleshooting

- **Aplikasi gagal start / module not found**: pastikan dependencies ter-install (lihat **Instalasi**) dan Anda menjalankan dari folder proyek.
- **Data tidak muncul**: cek apakah `data_app/history/history.csv` dan file target di `data_app/targets/` tersedia dan format CSV sesuai.
- **Konfigurasi tidak terbaca**: pastikan `data_app/settings/config.toml` ada dan tidak kosong.

