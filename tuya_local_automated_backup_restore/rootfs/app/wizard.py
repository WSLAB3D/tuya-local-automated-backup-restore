#!/usr/bin/env python3
"""Ingress web UI for the Tuya Local Backup & Restore app."""

from __future__ import annotations

import json
import logging
import secrets
import sys
from pathlib import Path
from typing import Any

from common import (
    add_new_entries,
    config_flow_post,
    discover_tuya_devices,
    entry_key,
    get_available_gateways,
    get_config_entries,
    get_record,
    is_tuya_local_installed,
    load_options,
    run_backup_restore,
    save_record,
    select_type_option,
)
from flask import Flask, flash, redirect, render_template, render_template_string, request, send_file, url_for
from jinja2 import BaseLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

LAST_RUN_PATH = Path("/data/last_run.json")
SECRET_PATH = Path("/data/secret.key")

if SECRET_PATH.exists():
    SECRET_KEY = SECRET_PATH.read_text(encoding="utf-8").strip()
else:
    SECRET_KEY = secrets.token_hex(32)
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRET_PATH.write_text(SECRET_KEY, encoding="utf-8")

class IngressMiddleware:
    """Make Flask URL generation work behind the Home Assistant Ingress proxy."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        ingress_path = environ.get("HTTP_X_INGRESS_PATH", "")
        if ingress_path:
            environ["SCRIPT_NAME"] = ingress_path.rstrip("/")
        return self.app(environ, start_response)


app = Flask(__name__)
app.secret_key = SECRET_KEY
app.wsgi_app = IngressMiddleware(app.wsgi_app)


def get_backup_path() -> Path:
    options = load_options()
    return Path(options.get("backup_path", "/config/tuya_local_device_records.json"))


def load_last_run() -> dict[str, Any] | None:
    if LAST_RUN_PATH.exists():
        with LAST_RUN_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_last_run(result: dict[str, Any]) -> None:
    LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LAST_RUN_PATH.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)


def get_status_context() -> dict[str, Any]:
    options = load_options()
    backup_path = get_backup_path()
    record = get_record(backup_path)
    last_run = load_last_run()
    return {
        "backup_path": str(backup_path),
        "device_count": len(record.get("tuya_local_devices", [])),
        "recorded_at": record.get("recorded_at"),
        "check_interval": options.get("check_interval_minutes", 60),
        "auto_restore": options.get("auto_restore", True),
        "auto_backup_new": options.get("auto_backup_new", True),
        "last_run": last_run,
        "tuya_local_installed": is_tuya_local_installed(),
    }


TEMPLATES: dict[str, str] = {
    "base.html": """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Tuya Local Backup & Restore{% endblock %}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2rem; background: #f5f5f5; color: #222; }
    .container { max-width: 960px; margin: auto; background: #fff; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    h1, h2 { margin-top: 0; }
    .muted { color: #666; }
    table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
    th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid #ddd; }
    th { background: #f0f0f0; }
    button, .button { display: inline-block; padding: 0.6rem 1.2rem; margin: 0.5rem 0.5rem 0.5rem 0; background: #03a9f4; color: #fff; border: none; border-radius: 4px; text-decoration: none; cursor: pointer; }
    button.secondary, .button.secondary { background: #9e9e9e; }
    input[type="file"] { margin: 0.5rem 0; }
    input[type="checkbox"] { transform: scale(1.2); margin: 0.5rem; }
    input[type="text"] { padding: 0.4rem; margin: 0.2rem; border: 1px solid #ddd; border-radius: 4px; width: 200px; }
    select { padding: 0.4rem; margin: 0.2rem; border: 1px solid #ddd; border-radius: 4px; }
    .alert { padding: 1rem; margin: 1rem 0; border-radius: 4px; }
    .alert.success { background: #e8f5e9; color: #2e7d32; }
    .alert.error { background: #ffebee; color: #c62828; }
    .alert.info { background: #e3f2fd; color: #1565c0; }
    pre { background: #263238; color: #aed581; padding: 1rem; overflow-x: auto; border-radius: 4px; }
  </style>
</head>
<body>
  <div class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="alert {{ category }}">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
  </div>
</body>
</html>""",
    "index.html": """{% extends "base.html" %}
{% block content %}
<h1>Tuya Local Automated Backup & Restore</h1>
<p class="muted">Back up and restore your tuya_local (LocalTuya) device configuration entries.</p>
{% if not tuya_local_installed %}
  <div class="alert error">The tuya_local integration was not found. Install it via HACS and add at least one device before using this app.</div>
{% elif device_count == 0 %}
  <div class="alert info">No backup devices found yet. Set up your devices in the tuya_local integration, then use the setup wizard to import them.</div>
  <a class="button" href="{{ url_for('setup') }}">Open setup wizard</a>
{% else %}
  <div class="alert success">Backup contains <strong>{{ device_count }}</strong> device(s).</div>
  <a class="button" href="{{ url_for('status') }}">View status</a>
  <a class="button secondary" href="{{ url_for('setup') }}">Import more devices</a>
  <a class="button secondary" href="{{ url_for('export_backup') }}">Export backup</a>
  <a class="button secondary" href="{{ url_for('discover_devices') }}">Import from Tuya Cloud</a>
{% endif %}
{% endblock %}""",
    "status.html": """{% extends "base.html" %}
{% block content %}
<h1>Status</h1>
<table>
  <tr><th>Setting</th><th>Value</th></tr>
  <tr><td>Backup path</td><td>{{ backup_path }}</td></tr>
  <tr><td>Backup devices</td><td>{{ device_count }}</td></tr>
  <tr><td>Last recorded</td><td>{{ recorded_at or "Never" }}</td></tr>
  <tr><td>Check interval</td><td>{{ check_interval }} minutes</td></tr>
  <tr><td>Auto restore</td><td>{{ auto_restore }}</td></tr>
  <tr><td>Auto back up new</td><td>{{ auto_backup_new }}</td></tr>
  <tr><td>tuya_local installed</td><td>{{ tuya_local_installed }}</td></tr>
</table>

{% if last_run %}
  <h2>Last run</h2>
  <pre>{{ last_run | tojson(indent=2) }}</pre>
{% endif %}

<form method="post" action="{{ url_for('run_now') }}" style="display:inline">
  <button type="submit">Run now</button>
</form>
<form method="post" action="{{ url_for('import_ha') }}" style="display:inline">
  <button type="submit" class="secondary">Import from existing tuya_local</button>
</form>
<a class="button secondary" href="{{ url_for('view_backup') }}">View backup</a>
<a class="button secondary" href="{{ url_for('export_backup') }}">Export backup</a>
<a class="button secondary" href="{{ url_for('discover_devices') }}">Import from Tuya Cloud</a>

<h2>Import backup file</h2>
<form method="post" action="{{ url_for('import_backup') }}" enctype="multipart/form-data">
  <input type="file" name="backup_file" accept=".json" required>
  <button type="submit" class="secondary">Import backup file</button>
</form>
{% endblock %}""",
    "setup.html": """{% extends "base.html" %}
{% block content %}
<h1>Setup wizard</h1>
<p class="muted">This app backs up and restores tuya_local config entries. It does not set up new Tuya devices from scratch.</p>

{% if not tuya_local_installed %}
  <div class="alert error">
    The tuya_local integration was not found in this Home Assistant installation.
    <ol>
      <li>Install <strong>tuya_local</strong> via HACS or manually.</li>
      <li>Add each Tuya device through the tuya_local integration.</li>
      <li>Return here and click <strong>Import from Home Assistant</strong>.</li>
    </ol>
  </div>
{% else %}
  <h2>1. Add your devices in tuya_local</h2>
  <p class="muted">Use the Home Assistant tuya_local integration (or the tinytuya wizard) to add each device first. Once they are working, return here.</p>

  <h2>2. Import existing tuya_local entries</h2>
  <p class="muted">Click below to copy the current tuya_local config entries into the backup file. The app will keep this backup in sync and restore missing devices automatically.</p>
  <form method="post" action="{{ url_for('import_ha') }}">
    <button type="submit">Import from Home Assistant</button>
  </form>
{% endif %}

<p><a class="button secondary" href="{{ url_for('index') }}">Back</a></p>
{% endblock %}""",
    "view_backup.html": """{% extends "base.html" %}
{% block content %}
<h1>Backup file</h1>
<pre>{{ content }}</pre>
<a class="button secondary" href="{{ url_for('status') }}">Back</a>
{% endblock %}""",
    "discover.html": """{% extends "base.html" %}
{% block content %}
<h1>Discover Tuya Devices</h1>
<p class="muted">Devices discovered on your local network that are not yet in Tuya Local.</p>

<div class="alert info">
  <strong>Important:</strong> This feature discovers devices but requires the local_key for each device. 
  You'll need to obtain the local_key from the Tuya/Smart Life app or use Tinytuya to extract it. 
  Without the local_key, devices cannot be added to Tuya Local.
</div>

{% if devices %}
<form method="post" action="{{ url_for('add_discovered_devices') }}">
  <table>
    <tr>
      <th>Select</th>
      <th>Device ID</th>
      <th>Name</th>
      <th>IP Address</th>
      <th>Type</th>
      <th>Local Key</th>
      <th>Template</th>
      <th>Gateway</th>
    </tr>
    {% for device in devices %}
    <tr>
      <td>
        <input type="checkbox" name="selected_devices" value='{{ device | tojson }}'>
      </td>
      <td>{{ device.device_id }}</td>
      <td>{{ device.name }}</td>
      <td>{{ device.ip }}</td>
      <td>{{ device.type }}</td>
      <td>
        <input type="text" name="local_key_{{ device.device_id }}" placeholder="Required" required>
      </td>
      <td>
        <select name="template_{{ device.device_id }}">
          <option value="">Auto-detect</option>
          <option value="kasa_socket">Kasa Socket</option>
          <option value="kasa_bulb">Kasa Bulb</option>
          <option value="garage_door">Garage Door</option>
          <option value="switch">Switch</option>
          <option value="fan">Fan</option>
          <option value="heater">Heater</option>
          <option value="humidifier">Humidifier</option>
          <option value="purifier">Air Purifier</option>
        </select>
      </td>
      <td>
        {% if device.is_gateway %}
          <select name="gateway_{{ device.device_id }}">
            <option value="">No Gateway</option>
            {% for gateway in gateways %}
              <option value="{{ gateway.device_id }}">{{ gateway.title }} ({{ gateway.device_id }})</option>
            {% endfor %}
          </select>
        {% else %}
          N/A
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </table>
  <button type="submit">Add Selected Devices</button>
</form>
{% else %}
  <div class="alert info">No new devices discovered. Make sure devices are powered on and connected to your network.</div>
{% endif %}

<p><a class="button secondary" href="{{ url_for('index') }}">Back</a></p>
{% endblock %}""",
}


class InlineLoader(BaseLoader):
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def get_source(self, environment, template: str):
        if template in self.mapping:
            return self.mapping[template], None, lambda: True
        raise FileNotFoundError(template)

    def list_templates(self):
        return sorted(self.mapping.keys())


app.jinja_loader = InlineLoader(TEMPLATES)


@app.route("/")
def index() -> Any:
    ctx = get_status_context()
    return render_template("index.html", **ctx)


@app.route("/status")
def status() -> Any:
    ctx = get_status_context()
    return render_template("status.html", **ctx)


@app.route("/setup")
def setup() -> Any:
    ctx = get_status_context()
    return render_template("setup.html", **ctx)


@app.route("/import_ha", methods=["POST"])
def import_ha() -> Any:
    if not is_tuya_local_installed():
        flash(
            "The tuya_local integration is not installed or has no config entries. "
            "Install it via HACS, set up at least one device, then return here.",
            "error",
        )
        return redirect(url_for("setup"))

    backup_path = get_backup_path()
    record = get_record(backup_path)
    entries = get_config_entries()
    current_by_key: dict[str, dict[str, Any]] = {}
    for e in entries.values():
        key = entry_key(e)
        if key:
            current_by_key[key] = e

    added = add_new_entries(record, current_by_key)
    if added:
        save_record(record, backup_path)
        flash(f"Imported {len(added)} device(s) from Home Assistant.", "success")
    else:
        flash("No new tuya_local devices found in Home Assistant.", "info")
    return redirect(url_for("status"))


@app.route("/run_now", methods=["POST"])
def run_now() -> Any:
    options = load_options()
    backup_path = get_backup_path()
    result = run_backup_restore(
        backup_path,
        auto_restore=bool(options.get("auto_restore", True)),
        auto_backup_new=bool(options.get("auto_backup_new", True)),
    )
    save_last_run(result)
    if result["success"]:
        flash("Backup/restore run completed successfully.", "success")
    else:
        flash("Backup/restore run completed with errors. See status for details.", "error")
    return redirect(url_for("status"))


@app.route("/view_backup")
def view_backup() -> Any:
    backup_path = get_backup_path()
    if backup_path.exists():
        content = backup_path.read_text(encoding="utf-8")
    else:
        content = '{"tuya_local_devices": []}'
    return render_template("view_backup.html", content=content)


@app.route("/api/backup")
def api_backup() -> Any:
    backup_path = get_backup_path()
    record = get_record(backup_path)
    return record


@app.route("/export_backup")
def export_backup() -> Any:
    """Export the backup JSON file for download."""
    backup_path = get_backup_path()
    if backup_path.exists():
        return send_file(
            backup_path,
            as_attachment=True,
            download_name="tuya_local_backup.json",
            mimetype="application/json"
        )
    else:
        flash("No backup file exists to export.", "error")
        return redirect(url_for("status"))


@app.route("/import_backup", methods=["POST"])
def import_backup() -> Any:
    """Import a backup JSON file and replace the current backup."""
    if "backup_file" not in request.files:
        flash("No file provided.", "error")
        return redirect(url_for("status"))
    
    file = request.files["backup_file"]
    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("status"))
    
    if not file.filename.endswith(".json"):
        flash("Please upload a JSON file.", "error")
        return redirect(url_for("status"))
    
    try:
        content = file.read().decode("utf-8")
        imported_data = json.loads(content)
        
        # Validate the structure
        if "tuya_local_devices" not in imported_data:
            flash("Invalid backup file: missing tuya_local_devices field.", "error")
            return redirect(url_for("status"))
        
        # Save the imported backup
        backup_path = get_backup_path()
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(content, encoding="utf-8")
        
        device_count = len(imported_data.get("tuya_local_devices", []))
        flash(f"Successfully imported backup with {device_count} device(s).", "success")
        return redirect(url_for("status"))
        
    except json.JSONDecodeError:
        flash("Invalid JSON file.", "error")
        return redirect(url_for("status"))
    except Exception as exc:
        flash(f"Error importing backup: {exc}", "error")
        return redirect(url_for("status"))


@app.route("/discover_devices")
def discover_devices() -> Any:
    """Discover Tuya devices on the local network."""
    if not is_tuya_local_installed():
        flash("Tuya Local must be installed first.", "error")
        return redirect(url_for("index"))
    
    try:
        # Get existing device IDs to filter out
        entries = get_config_entries()
        existing_ids = {entry.get("data", {}).get("device_id") for entry in entries.values()}
        
        # Discover devices
        discovered = discover_tuya_devices(existing_ids)
        
        # Get available gateways
        gateways = get_available_gateways()
        
        return render_template("discover.html", devices=discovered, gateways=gateways)
        
    except Exception as exc:
        flash(f"Error discovering devices: {exc}", "error")
        return redirect(url_for("index"))


@app.route("/add_discovered_devices", methods=["POST"])
def add_discovered_devices() -> Any:
    """Add selected discovered devices to Tuya Local."""
    if not is_tuya_local_installed():
        flash("Tuya Local must be installed first.", "error")
        return redirect(url_for("index"))
    
    try:
        selected_devices = request.form.getlist("selected_devices")
        if not selected_devices:
            flash("No devices selected.", "error")
            return redirect(url_for("discover_devices"))
        
        results = []
        success_count = 0
        
        for device_json in selected_devices:
            device = json.loads(device_json)
            device_id = device["device_id"]
            ip = device["ip"]
            template = request.form.get(f"template_{device_id}", "")
            gateway_id = request.form.get(f"gateway_{device_id}", "")
            local_key = request.form.get(f"local_key_{device_id}", "")
            
            if not local_key:
                results.append(f"{device['name']}: Skipped - local key required")
                continue
            
            try:
                # Step 1: Init config flow
                result = config_flow_post(None, {"handler": "tuya_local"})
                flow_id = result["flow_id"]
                
                # Step 2: Choose manual setup
                result = config_flow_post(flow_id, {"setup_mode": "manual"})
                
                # Step 3: Submit device details
                local_data = {
                    "device_id": device_id,
                    "host": ip,
                    "local_key": local_key,
                    "protocol_version": "auto",
                    "poll_only": False,
                }
                
                if gateway_id:
                    local_data["device_cid"] = device_id
                    local_data["host"] = gateway_id
                
                result = config_flow_post(flow_id, local_data)
                
                # Step 4: Handle template selection if needed
                if result.get("step_id") == "select_type" and template:
                    options = (
                        result.get("data_schema", [{}])[0]
                        .get("selector", {})
                        .get("select", {})
                        .get("options", [])
                    )
                    # Try to match the selected template
                    type_value = select_type_option(options, template)
                    if type_value:
                        result = config_flow_post(flow_id, {"type": type_value})
                
                # Step 5: Choose name
                if result.get("step_id") == "choose_entities":
                    device_name = device.get("name", f"Device {device_id}")
                    result = config_flow_post(flow_id, {"name": device_name})
                
                if result.get("type") == "create_entry":
                    results.append(f"{device['name']}: Successfully added")
                    success_count += 1
                else:
                    results.append(f"{device['name']}: Failed - {result.get('type', 'unknown error')}")
                    
            except Exception as device_exc:
                results.append(f"{device['name']}: Error - {device_exc}")
        
        # Run backup after successful additions
        if success_count > 0:
            try:
                backup_path = get_backup_path()
                backup_result = run_backup_restore(
                    backup_path,
                    auto_restore=False,
                    auto_backup_new=True,
                )
                save_last_run(backup_result)
            except Exception as backup_exc:
                results.append(f"Backup after addition failed: {backup_exc}")
        
        flash(f"Added {success_count}/{len(selected_devices)} device(s). Details: {', '.join(results)}", 
              "success" if success_count > 0 else "error")
        return redirect(url_for("status"))
        
    except Exception as exc:
        flash(f"Error adding devices: {exc}", "error")
        return redirect(url_for("discover_devices"))


if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=8099, threads=4, ident="Tuya Local Backup")
