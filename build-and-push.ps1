# Build e Push da Imagem Docker - Music Download para ZimaOS
# Script PowerShell para Windows

# Configuracoes
$IMAGE_NAME = "music-download"
$VERSION = "7.1"
$REGISTRY_USER = $env:DOCKER_USERNAME
$BUILD_TAG = if ($REGISTRY_USER) { "$REGISTRY_USER/$IMAGE_NAME`:$VERSION" } else { "$IMAGE_NAME`:$VERSION" }
$LATEST_TAG = if ($REGISTRY_USER) { "$REGISTRY_USER/$IMAGE_NAME`:latest" } else { "$IMAGE_NAME`:latest" }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Docker Build and Push - Music Download" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Build Tag: $BUILD_TAG" -ForegroundColor Yellow
Write-Host "Latest Tag: $LATEST_TAG" -ForegroundColor Yellow
Write-Host ""

# 1. Verificar se docker esta instalado
Write-Host "[1/4] Verificando Docker..." -ForegroundColor Cyan
try {
    docker --version | Out-Null
    Write-Host "OK - Docker encontrado" -ForegroundColor Green
} catch {
    Write-Host "ERRO - Docker nao esta instalado!" -ForegroundColor Red
    exit 1
}

# 2. Fazer login no Docker
Write-Host ""
Write-Host "[2/4] Verificando autenticacao Docker..." -ForegroundColor Cyan
if (-not $REGISTRY_USER) {
    Write-Host "AVISO - DOCKER_USERNAME nao definida" -ForegroundColor Yellow
    Write-Host "Fazendo login no Docker Hub..." -ForegroundColor Yellow
    docker login
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERRO - Login falhou!" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "OK - Usando usuario: $REGISTRY_USER" -ForegroundColor Green
}

# 3. Build da imagem
Write-Host ""
Write-Host "[3/4] Construindo imagem Docker..." -ForegroundColor Cyan
Write-Host "Isso pode levar alguns minutos..." -ForegroundColor Gray
Write-Host ""

docker build -t "$BUILD_TAG" -t "$LATEST_TAG" .

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO - Build falhou!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "OK - Build concluido com sucesso" -ForegroundColor Green

# 4. Push para Docker Hub
Write-Host ""
Write-Host "[4/4] Enviando imagem para Docker Hub..." -ForegroundColor Cyan
Write-Host "Isso pode levar alguns minutos..." -ForegroundColor Gray
Write-Host ""

docker push "$BUILD_TAG"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO - Push da versao falhou!" -ForegroundColor Red
    exit 1
}

docker push "$LATEST_TAG"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO - Push do latest falhou!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "OK - Push concluido com sucesso" -ForegroundColor Green

# Resultado final
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Sucesso! Imagem pronta para ZimaOS" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Versao especifica:" -ForegroundColor Cyan
Write-Host "  $BUILD_TAG" -ForegroundColor Yellow
Write-Host ""
Write-Host "Versao latest:" -ForegroundColor Cyan
Write-Host "  $LATEST_TAG" -ForegroundColor Yellow
Write-Host ""
Write-Host "Proximos passos no ZimaOS:" -ForegroundColor Cyan
Write-Host "  docker pull $LATEST_TAG" -ForegroundColor Yellow
Write-Host "  docker-compose up -d" -ForegroundColor Yellow
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
