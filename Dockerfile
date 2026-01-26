# Usamos o Ubuntu 22.04 como base (Equilíbrio entre modernidade e compatibilidade)
FROM ubuntu:22.04

# Configurações de ambiente
ENV DEBIAN_FRONTEND=noninteractive
ENV RUNNING_IN_DOCKER=true
# Adiciona Go e Bento4 ao PATH global
ENV PATH="/usr/local/go/bin:/app/bento4/bin:${PATH}"

# 1. Instalar dependências de sistema (ffmpeg, python, git, etc)
RUN apt-get update && apt-get install -y \
    python3 python3-pip ffmpeg git wget unzip gpac ca-certificates curl gnupg \
    && rm -rf /var/lib/apt/lists/*

# 2. Instalar libssl1.1 (Necessário para o Bento4 funcionar no Ubuntu 22.04)
RUN echo "deb http://security.ubuntu.com/ubuntu focal-security main" | tee /etc/apt/sources.list.d/focal-security.list \
    && apt-get update && apt-get install -y libssl1.1 \
    && rm /etc/apt/sources.list.d/focal-security.list && apt-get update

# 3. Instalar Go 1.23.2 (Versão oficial mais recente)
RUN wget -q https://go.dev/dl/go1.23.2.linux-amd64.tar.gz \
    && rm -rf /usr/local/go && tar -C /usr/local -xzf go1.23.2.linux-amd64.tar.gz \
    && rm go1.23.2.linux-amd64.tar.gz

# 4. Link simbólico Python
RUN ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /app

# 5. Instalar dependências Python
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 6. Setup Bento4 (Baixar e configurar durante o build)
RUN mkdir -p bento4 && \
    wget -q https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip -O bento4.zip && \
    unzip -q bento4.zip -d bento4 && rm bento4.zip && \
    # Organizar binários e dar permissão de execução
    mv bento4/Bento4-SDK-1-6-0-641.x86_64-unknown-linux/bin/* bento4/ && \
    chmod -R +x bento4

# 7. Setup Wrapper
RUN mkdir -p wrapper && \
    wget -q https://github.com/WorldObservationLog/wrapper/releases/download/Wrapper.x86_64.0df45b5/Wrapper.x86_64.0df45b5.zip -O wrapper.zip && \
    unzip -q wrapper.zip -d wrapper && rm wrapper.zip && \
    chmod +x wrapper/wrapper

# 8. Setup Downloader (Clone e pré-download de módulos Go)
RUN git clone https://github.com/zhaarey/apple-music-downloader apple-music-downloader && \
    cd apple-music-downloader && \
    go mod download

# 9. Copiar código da aplicação
COPY . .

EXPOSE 5000
CMD ["python", "main.py"]