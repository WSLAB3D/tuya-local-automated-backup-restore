#!/usr/bin/env python3
"""Ingress web UI for the Tuya Local Backup & Restore add-on."""

from __future__ import annotations

import json
import logging
import secrets
import sys
from pathlib import Path
from typing import Any

from common import (
    add_new_entries,
    entry_key,
    get_config_entries,
    get_record,
    is_tuya_local_installed,
    load_options,
    run_backup_restore,
    save_record,
)
from flask import Flask, flash, redirect, render_template, render_template_string, request, url_for
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
  <div class="alert error">The tuya_local integration was not found. Install it via HACS and add at least one device before using this add-on.</div>
{% elif device_count == 0 %}
  <div class="alert info">No backup devices found yet. Set up your devices in the tuya_local integration, then use the setup wizard to import them.</div>
  <a class="button" href="{{ url_for('setup') }}">Open setup wizard</a>
{% else %}
  <div class="alert success">Backup contains <strong>{{ device_count }}</strong> device(s).</div>
  <a class="button" href="{{ url_for('status') }}">View status</a>
  <a class="button secondary" href="{{ url_for('setup') }}">Import more devices</a>
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
{% endblock %}""",
    "setup.html": """{% extends "base.html" %}
{% block content %}
<h1>Setup wizard</h1>
<p class="muted">This add-on backs up and restores tuya_local config entries. It does not set up new Tuya devices from scratch.</p>

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
  <p class="muted">Click below to copy the current tuya_local config entries into the backup file. The add-on will keep this backup in sync and restore missing devices automatically.</p>
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
    return render_template("setup.html")


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


if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=8099, threads=4, ident="Tuya Local Backup")
