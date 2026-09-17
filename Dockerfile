# Dockerfile para Music-Download (linux/amd64 / x86-64)
# Stack: Flask + Socket.IO + Go downloader + wrapper nativo + FFmpeg + Bento4
FROM ubuntu:20.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RUNNING_IN_DOCKER=true \
    PATH="/usr/local/go/bin:/app/bento4/bin:/app/wrapper:${PATH}"

WORKDIR /app

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

# libssl1.1 para Bento4 x86-64/amd64
RUN curl -fL \
       https://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.24_amd64.deb \
       -o /tmp/libssl1.1.deb \
    && dpkg -i /tmp/libssl1.1.deb \
    && rm -f /tmp/libssl1.1.deb

# Go 1.23.2 para compilar/rodar o downloader Go no container
ARG GO_VERSION=1.23.2
RUN curl -fL \
       "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" \
       -o /tmp/go.tar.gz \
    && rm -rf /usr/local/go \
    && tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm -f /tmp/go.tar.gz

# Python aponta para python3 para compatibilidade
RUN ln -sf /usr/bin/python3 /usr/bin/python

# Instala dependências Python da aplicação
COPY requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir -r requirements.txt

# Bento4 SDK x86-64
ARG BENTO4_VERSION=1-6-0-641
RUN mkdir -p /app/bento4/bin \
    && curl -fL \
       "https://www.bok.net/Bento4/binaries/Bento4-SDK-${BENTO4_VERSION}.x86_64-unknown-linux.zip" \
       -o /tmp/bento4.zip \
    && unzip -q /tmp/bento4.zip -d /tmp/bento4-src \
    && cp -a \
       "/tmp/bento4-src/Bento4-SDK-${BENTO4_VERSION}.x86_64-unknown-linux/bin/." \
       /app/bento4/bin/ \
    && chmod -R a+rx /app/bento4/bin \
    && rm -rf /tmp/bento4-src /tmp/bento4.zip

# Wrapper da autenticação do Apple Music para x86-64
RUN mkdir -p /app/wrapper \
    && curl -fL \
       https://github.com/itouakirai/wrapper/releases/download/x86/wrapper.x86 \
       -o /app/wrapper/wrapper \
    && chmod +x /app/wrapper/wrapper

# Clona o downloader Go e baixa as dependências do módulo
RUN git clone --depth 1 \
       https://github.com/zhaarey/apple-music-downloader \
       /app/apple-music-downloader \
    && cd /app/apple-music-downloader \
    && go mod download

# Copia o código da aplicação web
COPY . /app

# Estruturas persistentes esperadas pela aplicação
RUN mkdir -p /app/data /app/downloads /app/config

EXPOSE 5000

CMD ["python", "main.py"]