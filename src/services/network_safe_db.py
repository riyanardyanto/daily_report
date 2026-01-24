"""
Improved SQLite configuration untuk shared network folder.

Perubahan dari konfigurasi default:
1. DISABLE WAL mode (WAL corrupts di network drives)
2. Enable DELETE journal mode (lebih safe untuk network)
3. Increase busy_timeout drastis
4. Add retry logic dengan exponential backoff
5. Add file-level locking sebelum database access
"""

from __future__ import annotations

import contextlib
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def _configure_connection_network_safe(conn: sqlite3.Connection) -> None:
    """
    Configure SQLite connection untuk network/shared folder.

    PENTING:
    - JANGAN gunakan WAL mode di network drive (causes corruption)
    - Gunakan DELETE journal mode instead
    - Set FULL synchronous untuk data integrity
    - Increase timeout untuk handle network latency
    """
    conn.execute("PRAGMA foreign_keys = ON")

    # CRITICAL: WAL mode TIDAK BOLEH di network drive!
    # WAL membutuhkan shared memory yang tidak reliable di network
    conn.execute("PRAGMA journal_mode = DELETE")  # Bukan WAL!

    # FULL synchronous lebih lambat tapi lebih aman di network
    conn.execute("PRAGMA synchronous = FULL")  # Bukan NORMAL!

    conn.execute("PRAGMA temp_store = MEMORY")

    # Increase timeout untuk handle network latency
    # 30 detik untuk network yang lambat
    conn.execute("PRAGMA busy_timeout = 30000")  # 30 seconds

    # Cache size untuk performance
    conn.execute("PRAGMA cache_size = -2000")  # 2MB cache


def retry_on_locked(
    func: Callable[..., T],
    max_retries: int = 5,
    initial_delay: float = 0.1,
    max_delay: float = 5.0,
) -> Callable[..., T]:
    """
    Decorator untuk retry operation jika database locked.

    Args:
        max_retries: Maximum retry attempts
        initial_delay: Initial delay dalam seconds
        max_delay: Maximum delay dalam seconds (exponential backoff)
    """

    def wrapper(*args: Any, **kwargs: Any) -> T:
        delay = initial_delay
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)

            except sqlite3.OperationalError as e:
                last_error = e
                error_msg = str(e).lower()

                # Retry hanya untuk locked/busy errors
                if "locked" in error_msg or "busy" in error_msg:
                    if attempt < max_retries:
                        # Exponential backoff dengan jitter
                        import random

                        jitter = random.uniform(0, delay * 0.1)
                        sleep_time = min(delay + jitter, max_delay)

                        print(
                            f"Database locked, retry {attempt + 1}/{max_retries} after {sleep_time:.2f}s"
                        )
                        time.sleep(sleep_time)

                        # Exponential backoff
                        delay = min(delay * 2, max_delay)
                        continue

                # Error lain atau max retries reached
                raise

            except Exception:
                # Error non-locking, langsung raise
                raise

        # Jika sampai sini, semua retry gagal
        raise last_error

    return wrapper


@contextlib.contextmanager
def file_lock_context(db_path: Path, timeout: float = 30.0):
    """
    Context manager untuk file-level locking.
    Gunakan sebelum access SQLite untuk prevent concurrent write.

    Args:
        db_path: Path ke database file
        timeout: Maximum wait time untuk acquire lock
    """
    import sys

    if sys.platform == "win32":
        # Windows file locking
        import msvcrt

        lock_file = Path(str(db_path) + ".lock")
        lock_file.parent.mkdir(parents=True, exist_ok=True)

        start_time = time.time()
        fp = None

        while True:
            try:
                # Try create/open lock file exclusively
                fp = open(lock_file, "w")
                msvcrt.locking(fp.fileno(), msvcrt.LK_NBLCK, 1)
                break

            except (IOError, OSError):
                # Lock file exists atau locked
                if time.time() - start_time > timeout:
                    raise TimeoutError(
                        f"Could not acquire lock for {db_path} after {timeout}s"
                    )

                time.sleep(0.1)

        try:
            yield
        finally:
            # Release lock
            if fp:
                try:
                    msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
                    fp.close()
                except Exception:
                    pass

                try:
                    lock_file.unlink(missing_ok=True)
                except Exception:
                    pass

    else:
        # Unix/Linux file locking
        import fcntl

        lock_file = Path(str(db_path) + ".lock")
        lock_file.parent.mkdir(parents=True, exist_ok=True)

        fp = open(lock_file, "w")

        start_time = time.time()
        while True:
            try:
                fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (IOError, OSError):
                if time.time() - start_time > timeout:
                    fp.close()
                    raise TimeoutError(
                        f"Could not acquire lock for {db_path} after {timeout}s"
                    )
                time.sleep(0.1)

        try:
            yield
        finally:
            try:
                fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
                fp.close()
            except Exception:
                pass

            try:
                lock_file.unlink(missing_ok=True)
            except Exception:
                pass


def connect_network_safe(db_path: Path) -> sqlite3.Connection:
    """
    Create SQLite connection yang aman untuk network/shared folder.

    PENTING: Gunakan dengan file_lock_context untuk write operations!

    Example:
        with file_lock_context(db_path):
            conn = connect_network_safe(db_path)
            # do write operations
            conn.commit()
    """
    conn = sqlite3.connect(
        db_path,
        timeout=30.0,  # Connection timeout
        isolation_level="DEFERRED",  # Lebih compatible dengan network
    )

    _configure_connection_network_safe(conn)
    return conn


# Example usage:
"""
from src.services.network_safe_db import (
    connect_network_safe,
    file_lock_context,
    retry_on_locked
)

# Untuk READ operation (bisa tanpa lock):
@retry_on_locked
def read_data(db_path: Path):
    conn = connect_network_safe(db_path)
    try:
        cursor = conn.execute("SELECT * FROM history_rows")
        return cursor.fetchall()
    finally:
        conn.close()

# Untuk WRITE operation (HARUS dengan lock):
@retry_on_locked
def write_data(db_path: Path, rows):
    with file_lock_context(db_path, timeout=30):
        conn = connect_network_safe(db_path)
        try:
            conn.executemany("INSERT INTO history_rows ...", rows)
            conn.commit()
        finally:
            conn.close()
"""
