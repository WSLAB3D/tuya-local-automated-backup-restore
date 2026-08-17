# Changelog

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
