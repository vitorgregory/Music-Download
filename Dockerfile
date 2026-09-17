# Dockerfile para Music-Download
# Stack real: Flask + Socket.IO + Go downloader + wrapper native + FFmpeg + Bento4
FROM ubuntu:22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RUNNING_IN_DOCKER=true \
    PATH="/usr/local/go/bin:/app/bento4/bin:${PATH}"

WORKDIR /app

# Dependências do sistema exigidas pela app e pelos binários externos
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv ffmpeg git wget unzip gpac ca-certificates curl gnupg \
    && rm -rf /var/lib/apt/lists/*

# libssl1.1 é necessário para o Bento4 funcionar em Ubuntu 22.04
RUN echo "deb http://security.ubuntu.com/ubuntu focal-security main" | tee /etc/apt/sources.list.d/focal-security.list \
    && apt-get update && apt-get install -y --no-install-recommends libssl1.1 \
    && rm -rf /var/lib/apt/lists/* /etc/apt/sources.list.d/focal-security.list \
    && apt-get update

# Go 1.23.2 para compilar/rodar o downloader Go no container
RUN wget -q https://go.dev/dl/go1.23.2.linux-amd64.tar.gz \
    && rm -rf /usr/local/go \
    && tar -C /usr/local -xzf go1.23.2.linux-amd64.tar.gz \
    && rm go1.23.2.linux-amd64.tar.gz

# Python aponta para python3 para facilitar compatibilidade
RUN ln -sf /usr/bin/python3 /usr/bin/python

# Instala dependências Python da aplicação
COPY requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# Bento4 SDK
RUN mkdir -p /app/bento4 && \
    wget -q https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip -O /tmp/bento4.zip && \
    unzip -q /tmp/bento4.zip -d /tmp/bento4-src && \
    mv /tmp/bento4-src/Bento4-SDK-1-6-0-641.x86_64-unknown-linux/bin/* /app/bento4/ && \
    chmod -R +x /app/bento4 && \
    rm -rf /tmp/bento4-src /tmp/bento4.zip

# Wrapper da autenticação do Apple Music
RUN mkdir -p /app/wrapper && \
    wget -q https://github.com/WorldObservationLog/wrapper/releases/download/Wrapper.x86_64.0df45b5/Wrapper.x86_64.0df45b5.zip -O /tmp/wrapper.zip && \
    unzip -q /tmp/wrapper.zip -d /tmp/wrapper-src && \
    cp /tmp/wrapper-src/wrapper /app/wrapper/wrapper && \
    chmod +x /app/wrapper/wrapper && \
    rm -rf /tmp/wrapper-src /tmp/wrapper.zip

# Clona o downloader Go e baixa dependências do módulo para reduzir tempo de boot
RUN git clone https://github.com/zhaarey/apple-music-downloader /app/apple-music-downloader && \
    cd /app/apple-music-downloader && \
    go mod download

# Copia código da aplicação web
COPY . /app

# Estruturas persistentes esperadas pela app
RUN mkdir -p /app/data /app/downloads /app/config

EXPOSE 5000

CMD ["python", "main.py"]