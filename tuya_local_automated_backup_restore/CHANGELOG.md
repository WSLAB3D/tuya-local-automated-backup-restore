# Changelog

## 0.0.7

- Removed privileged mode to avoid repository detection issues
- Keeping network: host for basic network access

## 0.0.6

- Added privileged mode for enhanced network access required for device discovery
- Logs show discovery running but finding 0 devices, so adding privileged mode

## 0.0.5

- Enhanced device discovery to show total devices found vs new devices
- Updated UI to display scan results with device counts
- Improved discovery function to return both total and new device counts

## 0.0.4

- Reverted map option back to "config:rw" to fix tuya_local integration detection

## 0.0.3

- Fixed deprecated map option (config -> homeassistant_config)
- Updated repository URL to correct capitalization (WSLAB3D)

## 0.0.2

- Fixed misleading warning message about local_key requirements
- Added debug logging for device discovery troubleshooting

## 0.0.1

- Initial release
- Device discovery from Tuya Cloud using Tinytuya
- JSON export/import for backup files
- Template and gateway selection for discovered devices
- Auto-backup after successful device addition
- Fixed Tinytuya device discovery function name

- Initial release
- Device discovery from Tuya Cloud using Tinytuya
- JSON export/import for backup files
- Template and gateway selection for discovered devices
- Auto-backup after successful device addition
- Fixed Tinytuya device discovery function name

- Added host network access for device discovery functionality

## 1.0.4

- Added device discovery feature to import devices from Tuya Cloud
- Added JSON export/import functionality for backup files
- Added Tinytuya dependency for local network device discovery
- Added UI for discovered devices with template and gateway selection
- Auto-runs backup after successful device addition

## 1.0.3

- Fixed setup wizard not detecting tuya_local installation when clicking "Import more devices"

## 1.0.2

- Replaced Flask's development server with `waitress` for production use in Ingress.

## 1.0.1

- Added Home Assistant Ingress path handling so the wizard's links work when opened through the HA sidebar.

## 1.0.0

- Initial release.
- Automatic backup and restore of `tuya_local` config entries.
- Ingress setup wizard to import from Home Assistant.
- Configurable check interval and backup path.
