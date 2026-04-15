# 🚀 Deploy da Imagem Docker no ZimaOS

## Pré-requisitos

✅ Ter Docker instalado  
✅ Estar logado no Docker Hub (ou registry privado)  
✅ Ter acesso ao repositório

---

## 📋 Opção 1: Build Local e Push (Recomendado)

### Passo 1: Configurar Docker Username

```bash
# Linux/Mac
export DOCKER_USERNAME="seu_usuario_docker"

# Windows PowerShell
$env:DOCKER_USERNAME = "seu_usuario_docker"
```

Substitua `seu_usuario_docker` com seu usuário no Docker Hub.

### Passo 2: Fazer Login no Docker Hub

```bash
docker login
```

Digite seu username e token/senha quando pedido.

### Passo 3: Executar Script de Build

**Linux/Mac:**
```bash
chmod +x build-and-push.sh
./build-and-push.sh
```

**Windows (PowerShell):**
```powershell
.\build-and-push.ps1
```

### Passo 4: Aguardar Conclusão

O script irá:
1. ✅ Build da imagem Docker
2. ✅ Tag versão e latest
3. ✅ Push para Docker Hub
4. ✅ Exibir URL pronta para ZimaOS

---

## 📋 Opção 2: Comandos Manuais

Se preferir executar manualmente:

```bash
# 1. Build
docker build -t seu_usuario/music-download:7.1 -t seu_usuario/music-download:latest .

# 2. Push da versão específica
docker push seu_usuario/music-download:7.1

# 3. Push da versão latest
docker push seu_usuario/music-download:latest
```

---

## 🔄 Atualizar no ZimaOS

### Opção A: Via Docker Compose

Se tem acesso ao arquivo `docker-compose.yml` no ZimaOS:

```yaml
services:
  music-download:
    image: seu_usuario/music-download:latest  # ← Atualizar para nova versão
    # ... resto da configuração
```

Depois:
```bash
docker-compose pull
docker-compose up -d
```

### Opção B: Via Portainer (Interface Web do ZimaOS)

1. Abra Portainer (http://zima-ip:9000)
2. Vá em **Containers**
3. Pare o container `apple-music-web` ou similar
4. Remova o container
5. Crie novo container com a nova imagem: `seu_usuario/music-download:latest`
6. Configure volumes e portas igual antes

### Opção C: Linha de Comando no ZimaOS

```bash
# SSH no ZimaOS
ssh root@zima-ip

# Parar e remover container antigo
docker stop apple-music-web-beta
docker rm apple-music-web-beta

# Pull da nova imagem
docker pull seu_usuario/music-download:latest

# Criar novo container
docker run -d \
  --name apple-music-web-beta \
  -p 5000:5000 \
  -v music-download-data:/app/data \
  -v music-download-downloads:/app/downloads \
  -v music-download-config:/app/apple-music-downloader \
  -e FLASK_DEBUG=0 \
  seu_usuario/music-download:latest
```

---

## 🔍 Verificar Status

### Verificar Build Local
```bash
docker images | grep music-download
```

### Verificar no Docker Hub
```bash
# Listar todas as tags
curl https://hub.docker.com/v2/repositories/seu_usuario/music-download/tags
```

### Verificar no ZimaOS
```bash
docker ps -a | grep music-download
docker logs apple-music-web-beta
```

---

## 📊 Informações da Imagem

### Tamanho
- Base: ~200 MB (Ubuntu 22.04)
- Dependências: ~400 MB (FFmpeg, Python, Go, etc)
- **Total esperado: ~600-800 MB**

### Componentes Inclusos
- ✅ Python 3 + Flask
- ✅ FFmpeg
- ✅ Go 1.23.2
- ✅ Bento4 (audio processing)
- ✅ Wrapper binary (autenticação)
- ✅ Apple Music Downloader

### Versões Atuais
- Python: 3.10
- Go: 1.23.2
- Bento4: 1.6.0
- Ubuntu: 22.04

---

## 🔐 Considerações de Segurança

### Public vs Private

**Se imagem pública (Docker Hub público):**
- ✅ Qualquer um pode usar
- ❌ Qualquer um pode ver o Dockerfile
- ⚠️ Não inclui credenciais Apple (seguro)

**Se imagem privada (requer autenticação):**
- ✅ Apenas você pode puxar
- ✅ Mais seguro
- ⚠️ Precisa configurar token/chave no ZimaOS

---

## 📝 Troubleshooting

### Erro: "unauthorized: authentication required"
```bash
docker login
# Tente novamente
```

### Erro: "cannot connect to Docker daemon"
```bash
# Certifique que Docker está rodando
docker ps

# Se Windows, inicie Docker Desktop
# Se Linux, inicie o serviço:
sudo systemctl start docker
```

### Erro: "disk space exhausted"
```bash
# Limpar imagens/containers antigos
docker system prune -a
```

### Push lento demais
- ✅ Verifique velocidade de internet
- ✅ Tente conectar em WiFi mais rápido
- ✅ ou conecte com Ethernet

---

## 📊 Checklist de Deploy

- [ ] Docker instalado localmente
- [ ] Login no Docker Hub
- [ ] DOCKER_USERNAME configurada (opcional mas recomendado)
- [ ] Executar build-and-push.sh ou build-and-push.ps1
- [ ] Aguardar push completar (5-10 minutos)
- [ ] Verificar imagem no Docker Hub
- [ ] Parar container antigo no ZimaOS
- [ ] Pull/criar novo container com nova imagem
- [ ] Testar funcionalidade
- [ ] Confirmar que dados foram preservados

---

## 🎯 Próximas Atualizações

Para futuras atualizações:

1. Fazer mudanças no código
2. Testar localmente: `docker-compose up --build`
3. Incrementar versão em `build-and-push.sh` ou `build-and-push.ps1`
4. Executar script novamente
5. Deploy no ZimaOS

---

## 📞 Suporte

Se tiver dúvidas:

1. Verifique os logs: `docker logs apple-music-web-beta`
2. Teste localmente primeiro: `docker-compose up --build`
3. Verifique conectividade: `docker ps`
4. Valide imagem: `docker inspect seu_usuario/music-download:latest`

---

**Boa sorte com o deploy! 🚀**
