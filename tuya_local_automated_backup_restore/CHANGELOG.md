# Changelog

## 1.0.6

- Fixed Tinytuya device discovery function name (deviceScan instead of deviceDiscovery)

## 1.0.5

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
