# Solusi SQLite di Shared Network Folder

## Masalah
Error `sqlite disk image is malformed` terjadi karena:
1. **WAL mode corrupt** di network drives (shared memory tidak reliable)
2. **Concurrent access** dari multiple komputer
3. **Network latency** menyebabkan timeout
4. **File locking** tidak reliable di SMB/CIFS shares

## ⚠️ PERINGATAN
**SQLite TIDAK DIRANCANG untuk multi-user network access!**
Dokumentasi resmi SQLite: https://www.sqlite.org/whentouse.html

---

## SOLUSI 1: Local SQLite + Sync Files (RECOMMENDED) ⭐

### Konsep
- Setiap komputer punya database SQLite **lokal** (di AppData)
- Data di-export ke shared folder sebagai JSON files
- Komputer lain import dari shared folder
- **TIDAK ADA concurrent access** ke file yang sama
- **TIDAK ADA corruption risk**

### Keuntungan
✅ Tidak ada database corruption
✅ Cepat (lokal access)
✅ Reliable
✅ Bisa offline, sync nanti
✅ Mudah backup (copy JSON files)

### Kerugian
❌ Tidak real-time (sync manual/periodic)
❌ Butuh logic untuk merge conflicts (jarang terjadi)

### Implementasi

#### 1. Setup Local Sync Service
```python
from pathlib import Path
from src.services.local_sync_db_service import LocalSyncDbService

# Get local AppData path
import os
local_db = Path(os.getenv('LOCALAPPDATA')) / 'DailyReport' / 'history.db'

# Shared folder tetap sama
sync_folder = Path(r'\\server\share\daily_report\sync')

# Initialize service
db_service = LocalSyncDbService(local_db, sync_folder)
```

#### 2. Ganti fungsi existing
```python
# SEBELUM (direct SQLite):
from src.services.history_db_service import append_history_rows
append_history_rows(db_path, rows)

# SESUDAH (local + sync):
db_service.append_rows(rows)
db_service.export_to_sync_folder()  # Sync ke shared folder
```

#### 3. Import data dari komputer lain
```python
# Saat aplikasi start atau periodic
imported_count = db_service.import_from_sync_folder()
print(f"Imported {imported_count} rows from other computers")
```

#### 4. Bidirectional sync (auto)
```python
# Panggil setiap X menit atau saat close aplikasi
imported, exported = db_service.sync_bidirectional()
print(f"Sync: imported {imported}, exported {exported} files")
```

### Migration dari DB existing
```python
from src.services.history_db_service import get_all_history_rows
from src.services.local_sync_db_service import LocalSyncDbService

# Read dari DB lama
old_db = Path(r'\\server\share\daily_report\history.db')
old_rows = get_all_history_rows(old_db)

# Write ke local DB baru
local_db = Path(os.getenv('LOCALAPPDATA')) / 'DailyReport' / 'history.db'
sync_folder = Path(r'\\server\share\daily_report\sync')

new_service = LocalSyncDbService(local_db, sync_folder)
new_service.append_rows(old_rows)

print(f"Migrated {len(old_rows)} rows to local database")
```

---

## SOLUSI 2: Improve Existing SQLite (Kurang Reliable)

### Jika HARUS tetap gunakan shared SQLite

#### 1. Disable WAL Mode
**PALING PENTING:** WAL mode CORRUPT di network drives!

```python
# SEBELUM (SALAH di network):
conn.execute("PRAGMA journal_mode = WAL")  # ❌ CORRUPT!

# SESUDAH (BENAR untuk network):
conn.execute("PRAGMA journal_mode = DELETE")  # ✅ Safe
```

#### 2. Increase Timeout & Synchronous
```python
conn.execute("PRAGMA busy_timeout = 30000")  # 30 detik
conn.execute("PRAGMA synchronous = FULL")    # Data integrity
```

#### 3. Add File Locking
```python
from src.services.network_safe_db import file_lock_context, connect_network_safe

# Untuk WRITE operations:
with file_lock_context(db_path, timeout=30):
    conn = connect_network_safe(db_path)
    conn.execute("INSERT INTO ...")
    conn.commit()
    conn.close()
```

#### 4. Add Retry Logic
```python
from src.services.network_safe_db import retry_on_locked

@retry_on_locked(max_retries=5)
def save_data(db_path, rows):
    with file_lock_context(db_path):
        conn = connect_network_safe(db_path)
        # ... write operations
        conn.commit()
        conn.close()
```

#### 5. Ganti `_configure_connection()` 
Dalam file `history_db_service.py`:
```python
# Import network safe config
from src.services.network_safe_db import _configure_connection_network_safe

# Ganti fungsi lama
def _configure_connection(conn: sqlite3.Connection) -> None:
    _configure_connection_network_safe(conn)
```

### Kelemahan Solusi 2
⚠️ Tetap bisa corruption (network unreliable)
⚠️ Lambat (banyak retries)
⚠️ Timeout jika banyak user simultan
⚠️ Butuh maintenance (cleanup locks)

---

## SOLUSI 3: Alternative Database

### Jika tidak bisa pakai DB server, alternatif lain:

#### A. JSON Files per User/Date
```
\\server\share\daily_report\data\
  ├── 2026-01-24_PC001.json
  ├── 2026-01-24_PC002.json
  └── 2026-01-23_PC001.json
```

Pros: Simple, no corruption
Cons: Perlu merge untuk query

#### B. CSV Files dengan Append-only
```python
# Setiap komputer append ke CSV terpisah
# Read operation: merge semua CSV
```

#### C. SQLite Browser/Reader Mode
- Satu komputer (server) punya write access
- Komputer lain read-only atau sync copy

---

## REKOMENDASI

### 1. Untuk Production (Multi-PC): 
✅ **SOLUSI 1** (Local SQLite + Sync)
- Paling reliable
- No corruption risk
- Good performance

### 2. Untuk Testing/Few Users:
⚙️ **SOLUSI 2** (Improved SQLite config)
- Quick fix existing code
- Masih ada risk

### 3. Untuk Future:
🚀 Consider lightweight server:
- **SQLite in Client-Server mode** (dengan Python HTTP API)
- **PostgreSQL/MySQL** minimal instance
- **Redis** untuk simple key-value

---

## Testing

### Test Corruption Resistance
```python
import concurrent.futures
from pathlib import Path

def write_test(db_path, worker_id):
    """Simulate concurrent writes"""
    for i in range(100):
        rows = [{"save_id": f"w{worker_id}_{i}", ...}]
        # Test your solution here
        db_service.append_rows(rows)

# Test dengan 5 workers concurrent
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(write_test, db_path, i) for i in range(5)]
    concurrent.futures.wait(futures)

print("Test completed - check for corruption")
```

### Test Network Latency
```python
import time

# Simulate network delay
time.sleep(0.5)  # 500ms delay
# Test operations
```

---

## Questions?

1. **Q: Bisa pakai database server di shared PC?**
   A: Ya, install PostgreSQL/MySQL di satu PC, access via network. Lebih reliable!

2. **Q: Berapa sering sync?**
   A: Recommend: Export saat save data, Import setiap 5-10 menit atau saat app start.

3. **Q: Bagaimana handle conflicts?**
   A: Gunakan unique constraints (save_id, timestamp). INSERT OR IGNORE untuk skip duplicates.

4. **Q: File JSON terlalu banyak?**
   A: Cleanup file lama (>7 hari) atau merge ke archive monthly.

---

## Migration Steps

### Step 1: Backup existing database
```bash
copy \\server\share\daily_report\history.db \\server\share\daily_report\history.db.backup
```

### Step 2: Choose solution
- Production: Implement Solusi 1
- Quick fix: Implement Solusi 2

### Step 3: Test dengan 2-3 PC

### Step 4: Deploy ke semua PC

### Step 5: Monitor untuk corruption

---

**Terakhir diupdate: 2026-01-24**
