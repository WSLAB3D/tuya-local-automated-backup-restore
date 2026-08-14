#!/usr/bin/env python3
"""Scheduled monitor for the Tuya Local Backup & Restore add-on."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from common import is_tuya_local_installed, load_options, run_backup_restore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
_LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up and restore tuya_local config entries.")
    parser.add_argument("--run-once", action="store_true", help="Run one cycle and exit.")
    args = parser.parse_args()

    options = load_options()
    backup_path = Path(options.get("backup_path", "/config/tuya_local_device_records.json"))
    check_interval = max(1, int(options.get("check_interval_minutes", 60))) * 60
    auto_restore = bool(options.get("auto_restore", True))
    auto_backup_new = bool(options.get("auto_backup_new", True))

    if args.run_once:
        _LOGGER.info("Running one backup/restore cycle")
        status = run_backup_restore(backup_path, auto_restore, auto_backup_new)
        print(json.dumps(status, indent=2, default=str))
        sys.exit(0 if status["success"] else 1)

    _LOGGER.info("Starting Tuya Local monitor (interval: %s minutes)", check_interval // 60)
    while True:
        if not is_tuya_local_installed():
            _LOGGER.error(
                "The tuya_local integration is not installed or has no config entries. "
                "Install it via HACS and add at least one device. Sleeping %s minutes before retrying.",
                check_interval // 60,
            )
            time.sleep(check_interval)
            continue

        try:
            run_backup_restore(backup_path, auto_restore, auto_backup_new)
        except Exception as exc:
            _LOGGER.exception("Backup/restore cycle failed: %s", exc)

        _LOGGER.info("Sleeping for %s minutes", check_interval // 60)
        time.sleep(check_interval)


if __name__ == "__main__":
    main()
