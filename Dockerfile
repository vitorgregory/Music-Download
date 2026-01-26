# Usamos o Ubuntu 22.04 (Suporte nativo ao GPAC/MP4Box)
FROM ubuntu:22.04

# Configurações de ambiente
ENV DEBIAN_FRONTEND=noninteractive
ENV RUNNING_IN_DOCKER=true
# Adiciona o novo Go ao PATH do sistema
ENV PATH="/usr/local/go/bin:${PATH}"

# 1. Instalar dependências do sistema (SEM golang-go do apt)
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    ffmpeg \
    git \
    wget \
    unzip \
    gpac \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 1.5. Instalar Go 1.23.2 Manualmente (Ubuntu repo é muito velho)
RUN wget https://go.dev/dl/go1.23.2.linux-amd64.tar.gz && \
    rm -rf /usr/local/go && \
    tar -C /usr/local -xzf go1.23.2.linux-amd64.tar.gz && \
    rm go1.23.2.linux-amd64.tar.gz

# Link simbólico para python -> python3
RUN ln -s /usr/bin/python3 /usr/bin/python

# Diretório de trabalho
WORKDIR /app

# 2. Instalar dependências Python
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 3. Baixar e configurar Bento4
RUN mkdir -p bento4 && \
    wget -q https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip -O bento4.zip && \
    unzip -q bento4.zip -d bento4 && \
    rm bento4.zip && \
    find /app/bento4 -name "mp4decrypt" -type f -exec ln -s {} /usr/local/bin/mp4decrypt \; && \
    find /app/bento4 -name "mp4dump" -type f -exec ln -s {} /usr/local/bin/mp4dump \;

# 4. Baixar e configurar Wrapper
RUN mkdir -p wrapper && \
    wget -q https://github.com/WorldObservationLog/wrapper/releases/download/Wrapper.x86_64.0df45b5/Wrapper.x86_64.0df45b5.zip -O wrapper.zip && \
    unzip -q wrapper.zip -d wrapper && \
    rm wrapper.zip && \
    chmod +x wrapper/wrapper

# 5. Clonar o Downloader
RUN git clone https://github.com/zhaarey/apple-music-downloader apple-music-downloader

# Copiar o restante do código
COPY . .

# Expor porta e iniciar
EXPOSE 5000
CMD ["python", "main.py"]