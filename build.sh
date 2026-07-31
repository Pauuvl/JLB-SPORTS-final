#!/usr/bin/env bash
# Build script para Render. Configúralo como Build Command en el servicio,
# o dispáralo automáticamente si usas render.yaml (ver ese archivo).
set -o errexit

pip install -r requirements.txt

# Aplica migraciones pendientes (crea las tablas si es la primera vez).
flask db upgrade
