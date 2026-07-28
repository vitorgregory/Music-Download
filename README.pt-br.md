# Music Download - Interface Web para Apple Music (v7)

Baixe músicas do Apple Music em múltiplos formatos (ALAC, AAC, Atmos) via interface web Docker com fila inteligente, retry automático e seleção de faixas.

## 🚀 Quick Start

### Pré-requisitos
- **Docker** & **Docker Compose**

### Instalação

1. Clone ou copie os arquivos para seu servidor
2. Navegue até a pasta do projeto
3. Execute:
   ```bash
   docker-compose up --build -d
   ```
4. Acesse: `http://localhost:5000`

## 📖 Como Usar

### 1. Login
- Clique em **"Login to Wrapper"**
- Digite email + senha do Apple Music
- Se pedir 2FA, um modal auto-aparece → Digite o código
- Aguarde "✓ Login successful"

### 2. Baixar Música
- Cole um link do Apple Music (álbum, artista, single, playlist)
- Escolha o formato: **ALAC** (sem perda) | **AAC** (com perda) | **Atmos** (espacial)
- Clique em **Download**
- Se solicitar seleção de faixa, um modal aparece → Selecione as faixas desejadas
- A tabela de fila mostra o progresso em tempo real:
  - 🟡 **Processando** → em andamento
  - 🟢 **Concluído** → pronto (auto-aparece)
  - 🔴 **Falhou** → erro ocorreu

### 3. Gerenciar Fila
- **Pausar**: Clique no botão pausa
- **Cancelar**: Clique no ✕ em qualquer item
- **Retry Automático**: Falhas são retentadas automaticamente (3 vezes)

## ⚙️ Configuração

Edite `docker-compose.yml` para ajustar:

```yaml
environment:
  STALL_TIMEOUT_SECONDS: 300    # Timeout para detectar travamento
  MAX_RETRIES: 3                # Tentativas máximas
  RETRY_BASE_SECONDS: 5         # Base para backoff exponencial
```

## 🐛 Problemas Comuns

### Download fica "Processando" por muito tempo
- **Primeiro download**: Normal (10+ min) enquanto autentica
- **Próximos**: Devem ser rápidos
- Verifique: `docker-compose logs -f`

### Modal não aparece ao selecionar faixa
- Recarregue a página do navegador
- Verifique Socket.IO nos logs

### Erro 401 (Token Expirado)
- Faça login novamente via "Login to Wrapper"
- Tarefas com erro 401 vão para "Letra Morta" após 3 tentativas

### Container não inicia
```bash
docker-compose down -v
docker-compose build --no-cache
docker-compose up
```

## 📁 Volumes

- `./downloads` → suas músicas aparecem aqui
- `./data` → credenciais e banco de dados persistentes

## 🔧 Para Desenvolvedores

### Testes
```bash
DISABLE_QUEUE_WORKER=1 pytest
```

### Estado da Fila
```bash
curl http://localhost:5000/api/state | jq '.queue'
```

### Componentes Externos Necessários
```bash
# Clone o downloader
git clone https://github.com/zhaarey/apple-music-downloader.git apple-music-downloader

# Coloque o binário wrapper
mkdir -p wrapper
cp /path/to/wrapper wrapper/wrapper
chmod +x wrapper/wrapper

# Rebuild
docker-compose up -d --build
```

## ℹ️ Stack

- **Backend**: Flask + Socket.IO + SQLite
- **Frontend**: Bootstrap 5 + Vanilla JS + Socket.IO
- **Downloader**: Go 1.23 + Bento4 + FFmpeg
- **Auth**: Apple Music Wrapper binary

## ⚠️ Aviso

Apenas para uso educacional e pessoal. Respeite os Termos de Serviço do Apple.

## 🙏 Créditos


- [@zhaarey](https://github.com/zhaarey) - apple-music-downloader + wrapper
- Comunidade Open Source
- Cliente recebe evento, auto-mostra modal com opções
