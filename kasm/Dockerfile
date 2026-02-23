FROM ubuntu:22.04

# Tools needed to download and run the Kasm installer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        sudo \
    && rm -rf /var/lib/apt/lists/*

ARG KASM_VERSION=1.18.1
ENV KASM_VERSION=${KASM_VERSION}

COPY init.sh /init.sh
RUN chmod +x /init.sh

ENTRYPOINT ["/init.sh"]
