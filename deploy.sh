#!/usr/bin/env bash
set -euo pipefail

# Ajuste estes valores conforme o seu ambiente.
# IMAGE: tag da imagem publicada no GHCR
# SERVICE: nome do serviço definido em docker-compose.yml
# VOLUMES: caminhos locais dos diretórios usados para persistência
IMAGE="ghcr.io/vitorgregory/music-download:latest"
SERVICE="music-download"
COMPOSE_FILE="docker-compose.yml"

# Exemplo de caminhos persistidos no host:
# - ./data:/app/data
# - ./downloads:/app/downloads
# - ./config:/app/apple-music-downloader

echo "[deploy] Pulling image: ${IMAGE}"
docker pull "${IMAGE}"

echo "[deploy] Updating container via docker compose"
# O comando abaixo recria o container com a nova imagem sem derrubar o restante do stack.
docker compose -f "${COMPOSE_FILE}" up -d --force-recreate "${SERVICE}"

echo "[deploy] Pruning old Docker images"
docker image prune -f

echo "[deploy] Finished successfully"
