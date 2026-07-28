#!/bin/bash
# Build e Push da Imagem Docker - Music Download para ZimaOS

# Configurações
IMAGE_NAME="music-download"
REGISTRY_USER="${DOCKER_USERNAME}"  # Definir variável de ambiente antes
VERSION="7.1"
BUILD_TAG="${REGISTRY_USER}/${IMAGE_NAME}:${VERSION}"
LATEST_TAG="${REGISTRY_USER}/${IMAGE_NAME}:latest"

echo "🐳 Music Download - Build e Push Docker"
echo "================================================"
echo "Image: $BUILD_TAG"
echo "Latest: $LATEST_TAG"
echo ""

# 1. Verificar se docker está instalado
if ! command -v docker &> /dev/null; then
    echo "❌ Docker não está instalado!"
    exit 1
fi

# 2. Fazer login no Docker (se necessário)
if [ -z "$REGISTRY_USER" ]; then
    echo "⚠️  DOCKER_USERNAME não está definida"
    echo "Faça login no Docker manualmente:"
    docker login
else
    echo "✅ Usando DOCKER_USERNAME: $REGISTRY_USER"
fi

# 3. Build da imagem
echo ""
echo "📦 Building image..."
docker build -t "$BUILD_TAG" -t "$LATEST_TAG" .

if [ $? -ne 0 ]; then
    echo "❌ Build falhou!"
    exit 1
fi

echo "✅ Build concluído"

# 4. Push para Docker Hub
echo ""
echo "🚀 Fazendo push para Docker Hub..."
docker push "$BUILD_TAG"
docker push "$LATEST_TAG"

if [ $? -ne 0 ]; then
    echo "❌ Push falhou!"
    exit 1
fi

echo "✅ Push concluído"
echo ""
echo "================================================"
echo "✨ Image pronta para ZimaOS:"
echo "   - $BUILD_TAG"
echo "   - $LATEST_TAG"
echo ""
echo "No ZimaOS, atualize para: $LATEST_TAG"
echo "================================================"
