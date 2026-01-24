"""
Quick Fix untuk existing history_db_service.py

Patch fungsi _configure_connection untuk network safety.
Apply ini jika ingin quick fix tanpa full refactor.

CARA PAKAI:
1. Backup file history_db_service.py
2. Apply changes di bawah manual, atau
3. Import patch di awal aplikasi

PERUBAHAN:
- Disable WAL mode → DELETE mode
- Increase timeout
- Change synchronous mode
"""

# ==================== PATCH 1: Configure Connection ====================

# REPLACE fungsi _configure_connection di history_db_service.py
# DARI:
"""
def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA busy_timeout = 3000")
"""

# KE:
"""
def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    
    # CRITICAL FIX: WAL mode TIDAK AMAN untuk network drives!
    # WAL requires shared memory yang unreliable di SMB/CIFS
    conn.execute("PRAGMA journal_mode = DELETE")  # Changed from WAL
    
    # FULL synchronous untuk data integrity di network
    conn.execute("PRAGMA synchronous = FULL")  # Changed from NORMAL
    
    conn.execute("PRAGMA temp_store = MEMORY")
    
    # Increase timeout drastis untuk network latency
    conn.execute("PRAGMA busy_timeout = 30000")  # 30s, was 3s
    
    # Additional safety
    conn.execute("PRAGMA cache_size = -2000")  # 2MB cache
"""


# ==================== PATCH 2: Add Retry Logic ====================

# TAMBAHKAN di atas fungsi append_history_rows:
"""
import time
from functools import wraps

def _retry_on_locked(max_retries=5, initial_delay=0.1):
    '''Retry decorator untuk handle database locked.'''
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_error = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    last_error = e
                    if "locked" in str(e).lower() or "busy" in str(e).lower():
                        if attempt < max_retries:
                            import random
                            jitter = random.uniform(0, delay * 0.1)
                            sleep_time = min(delay + jitter, 5.0)
                            time.sleep(sleep_time)
                            delay = min(delay * 2, 5.0)
                            continue
                    raise
                except Exception:
                    raise
            
            raise last_error
        return wrapper
    return decorator
"""

# GUNAKAN decorator di fungsi yang sering error:
"""
@_retry_on_locked(max_retries=5)
def append_history_rows(db_path: Path, rows: Iterable[dict[str, Any]]) -> int:
    # ... existing code
"""


# ==================== PATCH 3: Add File Locking ====================

# TAMBAHKAN di awal file:
"""
import sys
import contextlib

@contextlib.contextmanager
def _file_lock(db_path: Path, timeout=30.0):
    '''Simple file-level lock untuk Windows.'''
    if sys.platform != "win32":
        yield  # Skip di non-Windows
        return
    
    import msvcrt
    lock_file = Path(str(db_path) + ".lock")
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    
    start = time.time()
    fp = None
    
    while True:
        try:
            fp = open(lock_file, "w")
            msvcrt.locking(fp.fileno(), msvcrt.LK_NBLCK, 1)
            break
        except (IOError, OSError):
            if time.time() - start > timeout:
                raise TimeoutError(f"Lock timeout after {timeout}s")
            time.sleep(0.1)
    
    try:
        yield
    finally:
        if fp:
            try:
                msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
                fp.close()
                lock_file.unlink(missing_ok=True)
            except Exception:
                pass
"""

# WRAP fungsi write dengan lock:
"""
@_retry_on_locked(max_retries=5)
def append_history_rows(db_path: Path, rows: Iterable[dict[str, Any]]) -> int:
    ensure_history_db(db_path)
    
    with _file_lock(db_path):  # ADD THIS
        normalized = [_normalize_row(r) for r in rows]
        if not normalized:
            return 0
        
        # ... rest of existing code
"""


# ==================== PATCH 4: Disable WAL Cleanup ====================

# MODIFY _cleanup_wal_sidecars untuk tidak delete jika masih dipakai:
"""
def _cleanup_wal_sidecars(db_path: Path) -> None:
    # Jika journal_mode bukan WAL, hapus WAL files orphan
    try:
        for suffix in ("-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                # Check jika file tidak locked sebelum delete
                try:
                    # Try open exclusively
                    with open(p, "r+b") as f:
                        pass
                    # If successful, safe to delete
                    p.unlink()
                except (IOError, OSError, PermissionError):
                    # File locked, skip (mungkin masih dipakai)
                    pass
    except Exception:
        return
"""


# ==================== SUMMARY PATCH ====================

print("""
QUICK FIX SUMMARY:
==================

1. DISABLE WAL MODE (PALING PENTING!)
   journal_mode = DELETE (bukan WAL)

2. INCREASE TIMEOUT
   busy_timeout = 30000 (30 detik)

3. FULL SYNCHRONOUS
   synchronous = FULL (untuk integrity)

4. ADD RETRY LOGIC
   @_retry_on_locked decorator

5. ADD FILE LOCKING
   with _file_lock(db_path) pada write operations

APPLY PATCHES:
- Edit src/services/history_db_service.py
- Follow comments di atas
- Test dengan 2-3 komputer

WARNING:
- Masih bisa corruption (network unreliable)
- Lebih baik pakai Local+Sync solution
""")
