"""
Test script untuk validate solusi SQLite network corruption.

CARA PAKAI:
1. Test current fix: python test_db_network.py --test-current
2. Test local+sync: python test_db_network.py --test-sync
3. Stress test: python test_db_network.py --stress
"""

import argparse
import concurrent.futures
import random
import sys
import time
from datetime import datetime


def test_current_db_service():
    """Test current history_db_service dengan quick fix."""
    print("\n=== Testing Current DB Service (Quick Fix) ===\n")

    from src.services.history_db_service import (
        append_history_rows,
        count_history_rows,
        read_history_tail,
    )
    from src.utils.helpers import data_app_path

    # Test database
    test_db = data_app_path("test_history.db", folder_name="data_app/history")
    print(f"Test DB: {test_db}")

    # Create test data
    test_rows = [
        {
            "save_id": f"test_{i}",
            "card_index": str(i),
            "detail_index": "0",
            "action_index": "0",
            "user": "test_user",
            "link_up": "TEST",
            "shift": "1",
            "date_field": "2026-01-24",
            "saved_at": datetime.now().isoformat(),
            "issue": f"Test issue {i}",
            "detail_code": "CODE001",
            "detail_name": "Test detail",
            "action_text": "Test action",
        }
        for i in range(10)
    ]

    # Test append
    print("Testing append_history_rows...")
    count = append_history_rows(test_db, test_rows)
    print(f"✅ Appended {count} rows")

    # Test count
    print("\nTesting count_history_rows...")
    total = count_history_rows(test_db)
    print(f"✅ Total rows: {total}")

    # Test read
    print("\nTesting read_history_tail...")
    rows = read_history_tail(test_db, limit=5)
    print(f"✅ Read {len(rows)} rows")

    if rows:
        print("\nSample row:")
        print(f"  save_id: {rows[0].get('save_id')}")
        print(f"  issue: {rows[0].get('issue')}")

    print("\n✅ Current DB Service Test: PASSED")


def test_local_sync_service():
    """Test LocalSyncDbService."""
    print("\n=== Testing Local+Sync DB Service ===\n")

    from src.services.history_db_adapter import (
        append_history_rows,
        count_history_rows,
        get_local_db_path,
        get_sync_folder,
        manual_sync,
        print_sync_status,
    )

    print_sync_status()

    # Create test data
    test_rows = [
        {
            "save_id": f"sync_test_{i}_{time.time()}",
            "card_index": str(i),
            "detail_index": "0",
            "action_index": "0",
            "user": "sync_test_user",
            "link_up": "SYNC",
            "shift": "2",
            "date_field": "2026-01-24",
            "saved_at": datetime.now().isoformat(),
            "issue": f"Sync test issue {i}",
            "detail_code": "SYNC001",
            "detail_name": "Sync test detail",
            "action_text": "Sync test action",
        }
        for i in range(5)
    ]

    print("\nTesting append (with auto sync)...")
    count = append_history_rows(None, test_rows)  # db_path ignored
    print(f"✅ Appended {count} rows")

    print("\nTesting manual sync...")
    imported, exported = manual_sync()
    print(f"✅ Sync: imported={imported}, exported={exported}")

    print("\nTesting count...")
    total = count_history_rows(None)
    print(f"✅ Total rows: {total}")

    print("\nLocal DB location:")
    print(f"  {get_local_db_path()}")
    print("\nSync folder location:")
    print(f"  {get_sync_folder()}")

    # Check sync files
    sync_folder = get_sync_folder()
    if sync_folder.exists():
        sync_files = list(sync_folder.glob("sync_*.json"))
        print(f"\n✅ Sync files created: {len(sync_files)}")
        if sync_files:
            print(f"  Latest: {sync_files[-1].name}")

    print("\n✅ Local+Sync Service Test: PASSED")


def stress_test_concurrent_writes(num_workers=5, writes_per_worker=20):
    """Stress test dengan concurrent writes."""
    print(
        f"\n=== Stress Test: {num_workers} workers x {writes_per_worker} writes ===\n"
    )

    from src.services.history_db_service import append_history_rows
    from src.utils.helpers import data_app_path

    test_db = data_app_path("stress_test.db", folder_name="data_app/history")

    errors = []
    successes = []

    def worker_task(worker_id):
        """Simulate concurrent writes from different processes."""
        worker_errors = []
        worker_successes = 0

        for i in range(writes_per_worker):
            try:
                rows = [
                    {
                        "save_id": f"worker_{worker_id}_{i}_{time.time()}",
                        "card_index": str(i),
                        "detail_index": "0",
                        "action_index": "0",
                        "user": f"worker_{worker_id}",
                        "link_up": "STRESS",
                        "shift": str((worker_id % 3) + 1),
                        "date_field": "2026-01-24",
                        "saved_at": datetime.now().isoformat(),
                        "issue": f"Stress test {worker_id}_{i}",
                        "detail_code": "STRESS",
                        "detail_name": "Stress detail",
                        "action_text": "Stress action",
                    }
                ]

                append_history_rows(test_db, rows)
                worker_successes += 1

                # Random delay to simulate real usage
                time.sleep(random.uniform(0.01, 0.1))

            except Exception as e:
                worker_errors.append((worker_id, i, str(e)))

        return worker_successes, worker_errors

    # Run concurrent workers
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker_task, i) for i in range(num_workers)]

        for future in concurrent.futures.as_completed(futures):
            success_count, error_list = future.result()
            successes.append(success_count)
            errors.extend(error_list)

    elapsed = time.time() - start_time

    # Results
    total_successes = sum(successes)
    total_errors = len(errors)
    total_attempts = num_workers * writes_per_worker

    print("\n=== Stress Test Results ===")
    print(f"Duration: {elapsed:.2f}s")
    print(f"Total attempts: {total_attempts}")
    print(
        f"✅ Successes: {total_successes} ({100 * total_successes / total_attempts:.1f}%)"
    )
    print(f"❌ Errors: {total_errors} ({100 * total_errors / total_attempts:.1f}%)")

    if errors:
        print("\n⚠️  Error samples (first 5):")
        for worker_id, write_id, error in errors[:5]:
            print(f"  Worker {worker_id}, Write {write_id}: {error}")

    # Verdict
    error_rate = total_errors / total_attempts
    if error_rate == 0:
        print("\n🎉 EXCELLENT: No errors!")
    elif error_rate < 0.01:
        print("\n✅ GOOD: Error rate < 1%")
    elif error_rate < 0.05:
        print("\n⚠️  ACCEPTABLE: Error rate < 5%")
    else:
        print("\n❌ POOR: Error rate >= 5% - Consider migration to Local+Sync")

    return error_rate


def migration_helper():
    """Helper untuk migrate dari shared DB ke local+sync."""
    print("\n=== Migration Helper ===\n")

    from src.utils.helpers import data_app_path

    shared_db = data_app_path("history.db", folder_name="data_app/history")

    print(f"Current shared DB: {shared_db}")

    if not shared_db.exists():
        print("❌ Shared DB not found!")
        return

    print("DB exists: ✅")

    # Check size
    size_mb = shared_db.stat().st_size / (1024 * 1024)
    print(f"DB size: {size_mb:.2f} MB")

    # Confirm migration
    print("\n⚠️  Migration will:")
    print("  1. Copy all data to local database")
    print("  2. Export to sync folder")
    print("  3. Keep original DB intact (backup)")

    confirm = input("\nProceed with migration? [y/N]: ")

    if confirm.lower() != "y":
        print("Migration cancelled.")
        return

    from src.services.history_db_adapter import (
        migrate_from_shared_db,
        print_sync_status,
    )

    print("\nMigrating...")
    count = migrate_from_shared_db(shared_db)

    print(f"\n✅ Migration complete: {count} rows migrated")

    print_sync_status()


def main():
    parser = argparse.ArgumentParser(description="Test SQLite network fixes")

    parser.add_argument(
        "--test-current",
        action="store_true",
        help="Test current DB service (quick fix)",
    )

    parser.add_argument(
        "--test-sync", action="store_true", help="Test local+sync service"
    )

    parser.add_argument(
        "--stress", action="store_true", help="Run stress test (concurrent writes)"
    )

    parser.add_argument(
        "--migrate", action="store_true", help="Interactive migration helper"
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of concurrent workers for stress test",
    )

    parser.add_argument(
        "--writes", type=int, default=20, help="Writes per worker for stress test"
    )

    args = parser.parse_args()

    # If no args, show help
    if not any([args.test_current, args.test_sync, args.stress, args.migrate]):
        parser.print_help()
        return

    try:
        if args.test_current:
            test_current_db_service()

        if args.test_sync:
            test_local_sync_service()

        if args.stress:
            stress_test_concurrent_writes(args.workers, args.writes)

        if args.migrate:
            migration_helper()

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
