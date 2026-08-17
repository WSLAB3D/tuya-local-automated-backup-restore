# Tuya Local Automated Backup & Restore

A Home Assistant app that automatically backs up and restores your `tuya_local` (LocalTuya) device configuration entries.

## Requirements

- The `tuya_local` custom integration must be installed in Home Assistant (e.g., via HACS) and have at least one device configured.
- This app does not set up new Tuya devices from scratch; it only backs up and restores existing `tuya_local` config entries.

## What it does

- **Backs up** all existing `tuya_local` config entries to a JSON file.
- **Restores** any missing `tuya_local` entries automatically.
- **Auto-updates** the backup when you add new `tuya_local` devices.
- **Setup wizard** imports existing `tuya_local` devices into the backup.

## Installation

1. Add this repository to your Home Assistant App Store:
   ```
   https://github.com/wslab3d/tuya-local-automated-backup-restore
   ```
2. Install **Tuya Local Automated Backup & Restore**.
3. Configure the backup path and check interval, then start the app.
4. Open the app's **Ingress** panel to run the setup wizard or import devices.

## Configuration

| Option | Default | Description |
| --- | --- | --- |
| `backup_path` | `/config/tuya_local_device_records.json` | Where the backup JSON file is stored. |
| `check_interval_minutes` | `60` | How often to check for missing or new devices. |
| `auto_restore` | `true` | Re-create missing `tuya_local` entries from the backup. |
| `auto_backup_new` | `true` | Add any new `tuya_local` entries to the backup. |

## How the restore works

The app reads `/config/.storage/core.config_entries` directly to inspect `tuya_local` entries. If a device in the backup is missing from the live entries, it drives the Home Assistant config flow API to re-add it using the stored `device_id`, `local_key`, `host`, and `type`.

## License

MIT
