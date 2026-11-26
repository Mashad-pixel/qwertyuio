# TrayUP final updated package

## Contents

- `TrayUP/` is the active unified working project, based on the newest uploaded `TrayUP-fixes-4-8.zip`.
- `source_snapshots/` contains both uploaded ZIPs unchanged for reference and recovery.
- `MERGE_MANIFEST.csv` records SHA-256 hashes for files in the active project.

## Update notes included in the active project

See `TrayUP/CHANGES.md` and `TrayUP/FIXES.md`. They document the implemented changes in this snapshot, including real reporting API integration, admin menu API integration, password recovery, checkout customer details, idempotency request fingerprints, and the related backend/test updates.

## Verification performed while packaging

- Python source compilation: passed.
- JavaScript syntax checks with Node.js: passed.
- Full pytest suite: not run during this packaging step; do not interpret syntax checks as runtime or security certification.

The source snapshots are retained unchanged. The active project tree uses the newer `TrayUP-fixes-4-8.zip` files where paths conflict; it is not a claim that every feature is fully integrated or every outstanding issue has been fixed.
