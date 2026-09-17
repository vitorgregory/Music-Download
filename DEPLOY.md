# Deploy do Music-Download com GHCR + Docker Compose

Este guia mostra como publicar a imagem Docker da aplicação no GitHub Container Registry (GHCR) e atualizar o servidor de produção automaticamente após cada push na branch `main`.

## Visão geral do fluxo

1. Você faz push para a branch `main`.
2. O GitHub Actions faz build da imagem Docker.
3. A imagem é enviada para `ghcr.io`.
4. No servidor, um script executa `docker pull` e `docker compose up -d --force-recreate`.
5. O container é atualizado sem perder a persistência de dados em volumes.

---

## 1) Configurar o GitHub Container Registry

### 1.1. Verificar permissões do repositório

No GitHub, acesse:

- Settings
- Actions
- General
- Workflow permissions

Garanta que a opção "Read and write permissions" esteja habilitada para o workflow, caso o repositório use GitHub Packages/ghcr.

### 1.2. Autenticação do GitHub Actions

O workflow usa as credenciais automáticas do GitHub:

- `github.actor`
- `${{ secrets.GITHUB_TOKEN }}`

Não é necessário criar um secret manual para o registry em workflows públicos simples, porque o GitHub gera `GITHUB_TOKEN` automaticamente para o repositório. Para pacotes privados, pode ser necessário ajustar permissões.

> Observação: em repositórios privados, o pacote no GHCR pode exigir acesso explícito para puxar a imagem em outros ambientes.

---

## 2) Estrutura do Docker e do deploy

Este projeto já contém a stack necessária para rodar a aplicação:

- Python + Flask + Socket.IO
- Go downloader
- Wrapper para autenticação do Apple Music
- FFmpeg/Bento4 para processamento de áudio
- Porta web: `5000`

Os arquivos principais são:

- `Dockerfile`
- `docker-compose.yml`
- `.github/workflows/docker-publish.yml`
- `deploy.sh`

---

## 3) Preparar o servidor de produção

### 3.1. Instalar Docker + Docker Compose

Em um servidor Linux (Ubuntu/Debian, por exemplo):

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Verifique:

```bash
docker --version
docker compose version
```

### 3.2. Clonar o repositório

```bash
git clone https://github.com/vitorgregory/Music-Download.git
cd Music-Download
```

### 3.3. Ajustar o docker-compose.yml

Edite o arquivo `docker-compose.yml` no servidor com os paths e valores corretos para sua infraestrutura.

Exemplo base:

```yaml
services:
  music-download:
    image: ghcr.io/vitorgregory/music-download:latest
    container_name: music-download
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
      - ./downloads:/app/downloads
      - ./config:/app/apple-music-downloader
    environment:
      FLASK_DEBUG: "0"
      DISABLE_QUEUE_WORKER: "0"
```

Ajuste:

- `image`: use a imagem correta do GHCR
- `ports`: altere se a aplicação ficar atrás de proxy ou em outra porta
- `volumes`: use diretórios do host para persistência
- `environment`: configure variáveis conforme o uso real

### 3.4. Criar os diretórios locais

```bash
mkdir -p ./data ./downloads ./config
```

Se o app precisar de `config.yaml` dentro da pasta `config`, copie ou adapte o arquivo do downloader antes do primeiro boot.

---

## 4) Deploy inicial

Na pasta do repositório, rode:

```bash
docker compose pull
docker compose up -d --force-recreate
```

Ou, para usar o script pronto:

```bash
chmod +x deploy.sh
./deploy.sh
```

Verifique se a aplicação subiu corretamente:

```bash
docker ps
docker logs -f music-download
```

Teste a API:

```bash
curl http://localhost:5000/health
```

Se a rota `/health` não existir, confirme a aplicação no navegador e nos logs.

---

## 5) Fluxo de atualização automática

### Regras do processo

1. Faça um commit e push para a branch `main`.
2. O GitHub Actions executa o workflow `.github/workflows/docker-publish.yml`.
3. O build gera as tags:
   - `ghcr.io/vitorgregory/music-download:latest`
   - `ghcr.io/vitorgregory/music-download:<sha>`
4. O servidor recebe a nova imagem pelo `deploy.sh`.
5. O container é recriado com `docker compose up -d --force-recreate`.

### Rodando o deploy no servidor

No host de produção, faça:

```bash
cd /path/to/Music-Download
./deploy.sh
```

Esse script:

- faz `docker pull` da imagem mais recente
- executa `docker compose up -d --force-recreate`
- faz prune das imagens antigas

---

## 6) Observações de segurança

- Nunca deixe credenciais fixas no arquivo `docker-compose.yml`.
- Use variáveis de ambiente do host ou secrets do GitHub para valores sensíveis.
- Mantenha o repositório com permissões adequadas para `GITHUB_TOKEN` e `ghcr.io`.
- Se a aplicação estiver exposta na internet, considere proxy reverso com Nginx ou Caddy e TLS.

---

## 7) Watchtower (opcional)

O Watchtower pode atualizar o container automaticamente sem rodar o script manualmente.

### Instalar o Watchtower

```bash
docker run -d \
  --name watchtower \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --cleanup \
  --schedule "0 0 4 * * *"
```

### Atenção

- O Watchtower pode atualizar a imagem automaticamente sem controle manual.
- Recomendado para ambientes simples, mas o script `deploy.sh` oferece uma abordagem mais previsível e explícita.

---

## 8) Checklist final de produção

- [ ] GHCR configurado corretamente
- [ ] Workflow de build/push ativado
- [ ] Imagem publicada em `ghcr.io`
- [ ] `docker-compose.yml` ajustado para o ambiente
- [ ] Diretórios `./data`, `./downloads`, `./config` criados
- [ ] Deploy inicial executado com sucesso
- [ ] Porta `5000` aberta ou proxy configurado
- [ ] Logs do container conferidos
- [ ] Processo de rollback e manutenção documentado

---

## 9) Dicas para manutenção

Em caso de problema:

```bash
docker compose logs -f music-download
docker inspect music-download
docker ps -a
```

Se o container travar ou a imagem ficar antiga:

```bash
docker compose down
docker compose pull
docker compose up -d --force-recreate
```

Se precisar limpar artefatos antigos:

```bash
docker system prune -a
```

---

## 10) Conclusão

Com esse fluxo, a aplicação é construída automaticamente em CI/CD, publicada no GHCR e atualizada em produção via um script simples e confiável. Isso reduz erros manuais e melhora a disponibilidade da aplicação.
