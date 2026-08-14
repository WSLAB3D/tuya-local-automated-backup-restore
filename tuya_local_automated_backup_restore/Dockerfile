ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY rootfs/app/requirements.txt /app/
RUN pip3 install --no-cache-dir -r /app/requirements.txt

COPY rootfs /
RUN chmod +x /etc/services.d/*/run

LABEL \
  io.hass.name="Tuya Local Automated Backup & Restore" \
  io.hass.description="Back up and restore tuya_local config entries" \
  io.hass.type="addon" \
  io.hass.version="1.0.0"
