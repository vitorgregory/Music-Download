FROM ubuntu:22.04

# Configurações de ambiente
ENV DEBIAN_FRONTEND=noninteractive
ENV RUNNING_IN_DOCKER=true
ENV PATH="/usr/local/go/bin:/app/bento4/bin:${PATH}"

# 1. Instalar dependências de sistema e Go 1.23
RUN apt-get update && apt-get install -y \
    python3 python3-pip ffmpeg git wget unzip gpac ca-certificates curl gnupg \
    && rm -rf /var/lib/apt/lists/* \
    # Hack para libssl1.1 (Necessário para Bento4)
    && echo "deb http://security.ubuntu.com/ubuntu focal-security main" | tee /etc/apt/sources.list.d/focal-security.list \
    && apt-get update && apt-get install -y libssl1.1 \
    && rm /etc/apt/sources.list.d/focal-security.list && apt-get update \
    # Instalar Go
    && wget https://go.dev/dl/go1.23.2.linux-amd64.tar.gz \
    && rm -rf /usr/local/go && tar -C /usr/local -xzf go1.23.2.linux-amd64.tar.gz \
    && rm go1.23.2.linux-amd64.tar.gz \
    # Symlink Python
    && ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /app

# 2. Instalar dependências Python
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 3. Setup Bento4 (Baixar e configurar no build time)
RUN mkdir -p bento4 && \
    wget -q https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip -O bento4.zip && \
    unzip -q bento4.zip -d bento4 && rm bento4.zip && \
    # Mover binários para pasta limpa e dar permissão
    mv bento4/Bento4-SDK-1-6-0-641.x86_64-unknown-linux/bin/* bento4/ && \
    chmod -R +x bento4

# 4. Setup Wrapper
RUN mkdir -p wrapper && \
    wget -q https://github.com/WorldObservationLog/wrapper/releases/download/Wrapper.x86_64.0df45b5/Wrapper.x86_64.0df45b5.zip -O wrapper.zip && \
    unzip -q wrapper.zip -d wrapper && rm wrapper.zip && \
    chmod +x wrapper/wrapper

# 5. Setup Downloader (Clone e Build para performance)
RUN git clone https://github.com/zhaarey/apple-music-downloader apple-music-downloader && \
    cd apple-music-downloader && \
    go mod download

# 6. Copiar código da aplicação
COPY . .

EXPOSE 5000
CMD ["python", "main.py"]