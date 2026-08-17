"""Shared helpers for the Tuya Local Backup & Restore app."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import requests
import tinytuya

_LOGGER = logging.getLogger(__name__)

OPTIONS_PATH = Path("/data/options.json")
HA_CONFIG_ENTRIES_PATH = Path("/config/.storage/core.config_entries")
HA_API_BASE = "http://supervisor/core/api"


def load_options() -> dict[str, Any]:
    """Load the app options written by the Supervisor."""
    if OPTIONS_PATH.exists():
        with OPTIONS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def ha_token() -> str | None:
    """Return the Supervisor token that authorizes HA API calls."""
    return os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")


def ha_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {ha_token() or ''}",
        "Content-Type": "application/json",
    }


def ha_request(method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make an authenticated request to Home Assistant via the Supervisor proxy."""
    if not path.startswith("/"):
        path = "/" + path
    url = f"{HA_API_BASE}{path}"
    kwargs: dict[str, Any] = {"headers": ha_headers(), "timeout": 60}
    if data is not None:
        kwargs["json"] = data
    resp = requests.request(method, url, **kwargs)
    resp.raise_for_status()
    if resp.text:
        return resp.json()
    return {}


def get_config_entries() -> dict[str, dict[str, Any]]:
    """Return current tuya_local config entries keyed by entry_id."""
    raw = HA_CONFIG_ENTRIES_PATH.read_text(encoding="utf-8")
    storage = json.loads(raw)
    entries = {
        e["entry_id"]: e
        for e in storage.get("data", {}).get("entries", [])
        if e.get("domain") == "tuya_local"
    }

    # Overlay live state from the REST API
    try:
        live_entries = ha_request("GET", "/config/config_entries/entry")
        for e in live_entries:
            if e.get("domain") == "tuya_local" and e["entry_id"] in entries:
                entries[e["entry_id"]]["state"] = e.get("state", "unknown")
    except Exception as exc:
        _LOGGER.warning("Could not fetch live entry states: %s", exc)

    return entries


def is_tuya_local_installed() -> bool:
    """Return True if the tuya_local custom integration is installed or has entries."""
    manifest = Path("/config/custom_components/tuya_local/manifest.json")
    if manifest.exists():
        return True

    try:
        if HA_CONFIG_ENTRIES_PATH.exists():
            raw = HA_CONFIG_ENTRIES_PATH.read_text(encoding="utf-8")
            storage = json.loads(raw)
            return any(
                e.get("domain") == "tuya_local"
                for e in storage.get("data", {}).get("entries", [])
            )
    except Exception as exc:
        _LOGGER.warning("Could not determine tuya_local installation status: %s", exc)
    return False


def entry_key(entry: dict[str, Any]) -> str | None:
    """Return the unique key for a tuya_local config entry.

    For sub-devices, the unique_id is the device_cid. For standalone devices,
    the unique_id is the device_id.
    """
    return entry.get("unique_id") or entry.get("data", {}).get("device_id")


def record_key(record: dict[str, Any]) -> str:
    """Return the unique key for a backup record entry."""
    return record.get("device_cid") or record["device_id"]


def build_record_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Build a backup record entry from a live tuya_local config entry."""
    data = entry.get("data", {})
    return {
        "title": entry.get("title", ""),
        "entry_id": entry.get("entry_id", ""),
        "unique_id": entry.get("unique_id", ""),
        "device_id": data.get("device_id", ""),
        "device_cid": data.get("device_cid", ""),
        "host": data.get("host"),
        "local_key": data.get("local_key"),
        "protocol_version": data.get("protocol_version"),
        "poll_only": data.get("poll_only", False),
        "type": data.get("type"),
        "manufacturer": data.get("manufacturer"),
        "model": data.get("model"),
        "cloud_name": None,
        "cloud_local_key": None,
        "cloud_product_id": None,
        "cloud_category": None,
        "cloud_online": None,
        "discovered_ip": None,
        "discovered_version": None,
        "discovered_product_key": None,
    }


def get_record(path: Path) -> dict[str, Any]:
    """Load the backup record, creating an empty one if necessary."""
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "recorded_at": None,
        "tuya_local_devices": [],
    }


def save_record(record: dict[str, Any], path: Path) -> None:
    """Write the backup record to disk."""
    record["recorded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, default=str)
    _LOGGER.info("Saved backup record with %s devices to %s", len(record.get("tuya_local_devices", [])), path)


def config_flow_post(flow_id: str | None, data: dict[str, Any]) -> dict[str, Any]:
    """Post a step to the HA config flow API."""
    if flow_id:
        return ha_request("POST", f"/config/config_entries/flow/{flow_id}", data)
    return ha_request("POST", "/config/config_entries/flow", data)


def select_type_option(options: list[dict[str, Any]], record_type: str) -> str | None:
    """Find the select_type option value that matches the record type."""
    if not record_type:
        return None
    prefix = f"{record_type}||"
    for opt in options:
        value = opt.get("value", "")
        if value.startswith(prefix):
            return value
    return None


def re_add_device(record: dict[str, Any]) -> dict[str, Any]:
    """Re-add a single tuya_local device from the backup record."""
    device_id = record["device_id"]
    local_key = record["local_key"]
    host = record.get("discovered_ip") or record.get("host")
    protocol = str(record.get("protocol_version", "auto"))
    poll_only = record.get("poll_only", False)
    device_cid = record.get("device_cid", "")
    dev_type = record.get("type")
    title = record["title"]

    _LOGGER.info("Re-adding device %s (%s) at %s", device_id, title, host)

    # Step 1: init flow
    result = config_flow_post(None, {"handler": "tuya_local"})
    flow_id = result["flow_id"]

    # Step 2: choose manual setup
    result = config_flow_post(flow_id, {"setup_mode": "manual"})

    # Step 3: submit device details
    local_data = {
        "device_id": device_id,
        "host": host or "",
        "local_key": local_key,
        "protocol_version": protocol,
        "poll_only": poll_only,
    }
    if device_cid:
        local_data["device_cid"] = device_cid

    result = config_flow_post(flow_id, local_data)
    if result.get("type") == "abort" or result.get("errors"):
        raise RuntimeError(f"Local step failed: {result}")

    # Step 4: select device type (when there are multiple choices)
    if result.get("step_id") == "select_type":
        options = (
            result.get("data_schema", [{}])[0]
            .get("selector", {})
            .get("select", {})
            .get("options", [])
        )
        type_value = select_type_option(options, dev_type)
        if not type_value:
            raise RuntimeError(f"Could not find matching type option for {dev_type}. Options: {options}")
        result = config_flow_post(flow_id, {"type": type_value})

    # Step 5: choose name / entities
    if result.get("step_id") == "choose_entities":
        result = config_flow_post(flow_id, {"name": title})

    if result.get("type") == "create_entry":
        return result
    raise RuntimeError(f"Config flow did not create entry: {result}")


def reload_entry(entry_id: str) -> bool:
    """Reload a tuya_local config entry."""
    try:
        ha_request("POST", f"/config/config_entries/entry/{entry_id}/reload")
        return True
    except Exception as exc:
        _LOGGER.warning("Failed to reload entry %s: %s", entry_id, exc)
        return False


def ensure_device(record: dict[str, Any], current_by_key: dict[str, dict[str, Any]]) -> str:
    """Ensure a single device exists and is loaded. Returns a status string."""
    key = record_key(record)
    title = record["title"]

    if key in current_by_key:
        entry = current_by_key[key]
        state = entry.get("state", "unknown")
        if state == "loaded":
            return f"{title}: already loaded"
        _LOGGER.warning("%s entry exists but state is %s; attempting reload", title, state)
        if reload_entry(entry["entry_id"]):
            return f"{title}: reloaded (was {state})"
        return f"{title}: reload failed (state was {state})"

    try:
        result = re_add_device(record)
        return f"{title}: re-added as {result['result']['entry_id']}"
    except Exception as exc:
        _LOGGER.exception("Failed to re-add %s: %s", title, exc)
        return f"{title}: ERROR {exc}"


def add_new_entries(
    record: dict[str, Any],
    current_by_key: dict[str, dict[str, Any]],
    record_by_key: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Append any tuya_local entries that are not already in the backup record."""
    if record_by_key is None:
        record_by_key = {record_key(d): d for d in record.get("tuya_local_devices", [])}

    added: list[str] = []
    new_keys = set(current_by_key.keys()) - set(record_by_key.keys())
    for key in new_keys:
        entry = current_by_key[key]
        new_record = build_record_entry(entry)
        record.setdefault("tuya_local_devices", []).append(new_record)
        _LOGGER.info("Added new device to backup: %s (%s)", new_record["title"], key)
        added.append(f"{new_record['title']}: added to backup")
    return added


def discover_tuya_devices(existing_device_ids: set[str] | None = None) -> tuple[int, list[dict[str, Any]]]:
    """Discover Tuya devices on the local network using Tinytuya.
    
    Args:
        existing_device_ids: Set of device IDs already in Tuya Local to filter out
        
    Returns:
        Tuple of (total_devices_found, list_of_new_devices)
    """
    if existing_device_ids is None:
        existing_device_ids = set()
    
    discovered = []
    
    try:
        _LOGGER.info("Starting Tuya device discovery...")
        # Use Tinytuya's device discovery
        devices = tinytuya.deviceScan(verbose=False, maxretry=15, poll=False)
        _LOGGER.info("Device scan completed. Found %d devices total", len(devices))
        
        for dev_id, dev_info in devices.items():
            _LOGGER.info("Processing device: %s - Info: %s", dev_id, dev_info)
            # Skip devices already in Tuya Local
            if dev_id in existing_device_ids:
                _LOGGER.info("Skipping device %s - already in Tuya Local", dev_id)
                continue
            
            # Extract device information
            device_data = {
                "device_id": dev_id,
                "ip": dev_info.get("ip", ""),
                "name": dev_info.get("name", f"Device {dev_id}"),
                "product_key": dev_info.get("productKey", ""),
                "version": dev_info.get("version", ""),
                "is_gateway": dev_info.get("gwId", "") != "",  # Has gateway ID if it's a sub-device
                "type": dev_info.get("type", "unknown"),
            }
            
            _LOGGER.info("Discovered Tuya device: %s at %s", device_data["name"], device_data["ip"])
            discovered.append(device_data)
            
    except Exception as exc:
        _LOGGER.error("Error during Tuya device discovery: %s", exc)
        
    return len(devices), discovered


def get_available_gateways() -> list[dict[str, Any]]:
    """Get list of available Tuya gateways from existing Tuya Local entries.
    
    Returns:
        List of gateway devices with their information
    """
    gateways = []
    
    try:
        entries = get_config_entries()
        for entry_id, entry in entries.items():
            data = entry.get("data", {})
            # Check if this device is a gateway (has device_cid or is marked as gateway)
            if data.get("device_cid") or entry.get("title", "").lower().find("gateway") != -1:
                gateway_info = {
                    "entry_id": entry_id,
                    "title": entry.get("title", ""),
                    "device_id": data.get("device_id", ""),
                    "host": data.get("host", ""),
                }
                gateways.append(gateway_info)
                _LOGGER.info("Found gateway: %s (%s)", gateway_info["title"], gateway_info["device_id"])
                
    except Exception as exc:
        _LOGGER.warning("Error getting gateways: %s", exc)
        
    return gateways


def run_backup_restore(
    backup_path: Path,
    auto_restore: bool = True,
    auto_backup_new: bool = True,
) -> dict[str, Any]:
    """Run one backup/restore cycle."""
    record = get_record(backup_path)
    _LOGGER.info("Loaded backup record with %s devices from %s", len(record.get("tuya_local_devices", [])), backup_path)

    entries = get_config_entries()
    current_by_key: dict[str, dict[str, Any]] = {}
    for entry_id, e in entries.items():
        key = entry_key(e)
        if key:
            current_by_key[key] = e

    record_by_key = {record_key(d): d for d in record.get("tuya_local_devices", [])}

    _LOGGER.info("Found %s current tuya_local entries", len(entries))

    results: list[str] = []

    # Restore missing devices
    if auto_restore:
        for device in record.get("tuya_local_devices", []):
            results.append(ensure_device(device, current_by_key))

    # Back up new devices
    added: list[str] = []
    if auto_backup_new:
        added = add_new_entries(record, current_by_key, record_by_key)
        if added:
            save_record(record, backup_path)

    for r in results:
        _LOGGER.info(r)
    for a in added:
        _LOGGER.info(a)

    missing = [r for r in results if "ERROR" in r]
    errors = missing
    status = {
        "backup_path": str(backup_path),
        "total_backup_devices": len(record.get("tuya_local_devices", [])),
        "current_entries": len(entries),
        "restored_or_checked": results,
        "added": added,
        "errors": errors,
        "success": not errors,
    }
    _LOGGER.info("Run complete. Backup: %s devices. Errors: %s", status["total_backup_devices"], len(errors))
    return status
