# Fix SQLite "Disk Image is Malformed" di Shared Folder

## 🔴 Masalah
Aplikasi .exe di shared folder, multiple komputer, error:
```
sqlite.DatabaseError: disk image is malformed
```

**Root Cause:** SQLite tidak dirancang untuk concurrent network access!

---

## ✅ SOLUSI YANG SUDAH DITERAPKAN (Quick Fix)

Saya sudah apply **Quick Fix** pada [`history_db_service.py`](src/services/history_db_service.py):

### Perubahan:
1. ✅ **DISABLE WAL mode** → `DELETE` mode (aman untuk network)
2. ✅ **Increase timeout** → 30 detik (was 3s)  
3. ✅ **FULL synchronous** → Data integrity

### File yang diubah:
- `src/services/history_db_service.py` - fungsi `_configure_connection()`

### Testing:
```bash
# Test dengan aplikasi existing
uv run main.py
```

**Ekspektasi:** Error berkurang signifikan, tapi masih mungkin terjadi jika banyak user simultan.

---

## 🚀 SOLUSI LEBIH BAIK (Recommended untuk Production)

### Opsi 1: Local SQLite + Sync (BEST)

Setiap komputer pakai database **lokal** + sync via JSON files.

**Keuntungan:**
- ✅ **NO corruption risk**
- ✅ **Fast** (local access)
- ✅ **Reliable**

**Cara pakai:**

```python
# Ganti import:
# DARI:
from src.services.history_db_service import append_history_rows

# KE:
from src.services.history_db_adapter import append_history_rows

# Code tetap sama!
append_history_rows(db_path, rows)
```

**Migration:**
```python
from src.services.history_db_adapter import migrate_from_shared_db, print_sync_status

# Migrate data lama (run once per komputer)
shared_db = Path(r"\\server\share\daily_report\data_app\history\history.db")
migrate_from_shared_db(shared_db)

# Check status
print_sync_status()
```

**Auto sync:**
- Export: Otomatis setelah `append_history_rows()`
- Import: Setiap app start + manual trigger

---

## 📋 File Pendukung

### Dokumentasi Lengkap:
- [`NETWORK_DB_SOLUTIONS.md`](NETWORK_DB_SOLUTIONS.md) - Penjelasan detail semua solusi

### Code Baru:
1. **`src/services/local_sync_db_service.py`**
   - Core service untuk local DB + sync
   
2. **`src/services/history_db_adapter.py`**
   - Drop-in replacement untuk existing code
   - Compatible dengan API lama
   
3. **`src/services/network_safe_db.py`**
   - Utilities untuk network-safe SQLite (jika pakai Solusi 2)
   - Retry logic, file locking, dll

### Patches:
- **`QUICK_FIX_PATCHES.py`** - Manual patches (reference)

---

## 🎯 Rekomendasi

### Untuk Sekarang (Testing):
✅ **Quick fix sudah diterapkan** - test dulu apakah error berkurang

### Jika Error Masih Sering:
🚀 **Migrate ke Local+Sync** (Opsi 1)
- Lebih reliable
- Zero corruption risk
- 2 jam implementasi

### Jika Butuh Real-time:
💾 **Install database server** di salah satu PC
- PostgreSQL atau MySQL
- Set shared folder untuk backup saja

---

## 📝 Next Steps

1. **Test quick fix** (1-2 hari)
   - Monitor error frequency
   - Log setiap error

2. **Jika masih bermasalah:**
   ```python
   # Apply Opsi 1 (Local+Sync)
   # Ganti import di semua file:
   
   # File yang perlu diubah:
   # - src/app.py
   # - src/components/history_table.py
   ```

3. **Deploy bertahap:**
   - 1-2 PC test dulu
   - Monitor 1 minggu
   - Deploy ke semua PC

---

## ❓ FAQ

**Q: Kenapa WAL mode bermasalah?**
A: WAL butuh shared memory mapping yang unreliable di network drives (SMB/CIFS).

**Q: Apakah data aman dengan DELETE mode?**
A: Ya, DELETE mode lebih lambat tapi lebih aman untuk network.

**Q: Perlu restart aplikasi?**
A: Ya, setelah update code, restart semua instance aplikasi.

**Q: Bisakah pakai database server?**
A: Bisa! Install PostgreSQL/MySQL di satu PC, lebih reliable dari SQLite di network.

---

## 🔍 Monitoring

Check error log:
```python
# Tambahkan logging
import logging
logging.basicConfig(filename='db_errors.log', level=logging.ERROR)

try:
    append_history_rows(db_path, rows)
except Exception as e:
    logging.error(f"DB Error: {e}", exc_info=True)
```

---

**Updated:** 2026-01-24
**Status:** Quick Fix Applied ✅
**Next:** Monitor & Consider Local+Sync Migration
