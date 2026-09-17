# Dockerfile para Music-Download
# O projeto foi validado para servidores x86_64/amd64 e não deve baixar pacotes fixos de amd64 quando o build
# acontece em outra arquitetura. Para multi-arch, cada artefato externo precisa ter URL/arquitetura compatível.
FROM ubuntu:22.04 AS runtime

ARG TARGETARCH=amd64
ARG GO_VERSION=1.23.2
ARG BENTO4_VERSION=1-6-0-641

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RUNNING_IN_DOCKER=true \
    TARGETARCH=${TARGETARCH} \
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

# Wrapper da autenticação do Apple Music. Para produção x86_64 usa o binário x86; arm64 exige outro release do wrapper.
RUN mkdir -p /app/wrapper \
    && if [ "${TARGETARCH:-amd64}" = "amd64" ]; then \
         curl -fL https://github.com/itouakirai/wrapper/releases/download/x86/wrapper.x86 -o /app/wrapper/wrapper; \
       elif [ "${TARGETARCH:-amd64}" = "arm64" ]; then \
         echo "Unsupported arm64 build for wrapper binary in this project. Use linux/amd64 for production."; exit 1; \
       else \
         echo "Unsupported TARGETARCH=${TARGETARCH}"; exit 1; \
       fi \
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