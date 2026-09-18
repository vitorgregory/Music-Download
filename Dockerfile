# Dockerfile para music-download
# Usa a imagem oficial do wrapper como fonte do executável e do ambiente rootfs, conforme a estrutura validada em ghcr.io/itouakirai/wrapper:x86.
# O wrapper distribuído é x86_64; esta imagem é publicada para o ZimaOS em amd64.
FROM ghcr.io/itouakirai/wrapper:x86 AS wrapper

FROM ubuntu:22.04 AS runtime

ARG TARGETARCH
ARG GO_VERSION=1.23.2
ARG BENTO4_VERSION=1-6-0-641

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RUNNING_IN_DOCKER=true \
    WRAPPER_BIN=/app/wrapper \
    WRAPPER_ROOTFS=/app/rootfs \
    WRAPPER_CACHE_DIR=/app/config/wrapper \
    MUSIC_DOWNLOAD_WRAPPER=/app/wrapper \
    MUSIC_DOWNLOAD_WRAPPER_CACHE=/app/config/wrapper \
    TARGETARCH=${TARGETARCH} \
    PATH="/usr/local/go/bin:/app/bento4/bin:/app:${PATH}"

WORKDIR /app

# Evita gerar uma imagem arm64 incompatível com o wrapper x86 e o ZimaOS.
RUN test "${TARGETARCH:-amd64}" = "amd64" \
    || (echo "Este projeto suporta apenas linux/amd64; use --platform linux/amd64" >&2 && exit 1)

# Dependências do sistema exigidas pela aplicação e pelos binários externos
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       python3 \
       python3-pip \
       python3-venv \
       ffmpeg \
       git \
       wget \
       unzip \
       gpac \
       ca-certificates \
       curl \
       gnupg \
    && rm -rf /var/lib/apt/lists/*

# libssl1.1 precisa ser instalado na arquitetura correta do host/target; não faça download fixo de .deb amd64.
RUN echo "deb http://security.ubuntu.com/ubuntu focal-security main" > /etc/apt/sources.list.d/focal-security.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends libssl1.1 \
    && rm -f /etc/apt/sources.list.d/focal-security.list \
    && rm -rf /var/lib/apt/lists/*

# Go 1.23.2: usa o pacote correto da arquitetura alvo. Isso evita o erro de mismatch ao compilar em amd64/arm64.
RUN GO_ARCH="${TARGETARCH:-amd64}" \
    && if [ "$GO_ARCH" = "amd64" ]; then GO_OS_ARCH="linux-amd64"; elif [ "$GO_ARCH" = "arm64" ]; then GO_OS_ARCH="linux-arm64"; else echo "Unsupported GO_ARCH=$GO_ARCH" && exit 1; fi \
    && curl -fL "https://go.dev/dl/go${GO_VERSION}.${GO_OS_ARCH}.tar.gz" -o /tmp/go.tar.gz \
    && rm -rf /usr/local/go \
    && tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm -f /tmp/go.tar.gz

# Python aponta para python3 para compatibilidade
RUN ln -sf /usr/bin/python3 /usr/bin/python

# Instala dependências Python da aplicação
COPY requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir -r requirements.txt

# Bento4 SDK: o projeto atual é otimizado para x86_64/amd64. A checagem explícita mantém o build estável.
RUN BENTO4_ARCH="${TARGETARCH:-amd64}" \
    && if [ "$BENTO4_ARCH" = "amd64" ]; then BENTO4_PLATFORM="x86_64-unknown-linux"; elif [ "$BENTO4_ARCH" = "arm64" ]; then BENTO4_PLATFORM="arm64-unknown-linux"; else echo "Unsupported BENTO4_ARCH=$BENTO4_ARCH" && exit 1; fi \
    && mkdir -p /app/bento4/bin \
    && curl -fL "https://www.bok.net/Bento4/binaries/Bento4-SDK-${BENTO4_VERSION}.${BENTO4_PLATFORM}.zip" -o /tmp/bento4.zip \
    && unzip -q /tmp/bento4.zip -d /tmp/bento4-src \
    && cp -a "/tmp/bento4-src/Bento4-SDK-${BENTO4_VERSION}.${BENTO4_PLATFORM}/bin/." /app/bento4/bin/ \
    && chmod -R a+rx /app/bento4/bin \
    && rm -rf /tmp/bento4-src /tmp/bento4.zip

# Clona o downloader Go e baixa as dependências do módulo
RUN git clone --depth 1 \
       https://github.com/zhaarey/apple-music-downloader \
       /app/apple-music-downloader \
    && cd /app/apple-music-downloader \
    && go mod download

# Copia o código da aplicação web
COPY . /app

# Wrapper da autenticação do Apple Music.
# A imagem oficial já entrega o executável + raiz de runtime (/app/rootfs) completa, incluindo /app/rootfs/dev.
# Essas cópias ficam depois do contexto da aplicação para impedir sobrescrita acidental.
COPY --from=wrapper /app/wrapper /app/wrapper
COPY --from=wrapper /app/rootfs /app/rootfs

# Estruturas persistentes esperadas pela aplicação
RUN mkdir -p /app/data /app/downloads /app/config/wrapper /app/rootfs/dev /app/rootfs/data /app/rootfs/system \
    && chmod 0755 /app/wrapper

EXPOSE 5000

CMD ["python", "main.py"]