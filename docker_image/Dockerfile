FROM ubuntu:22.04

RUN \
    apt update && \
    apt install -y python3 python3-pip python3-venv \
    unzip wget curl bash ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN \
    wget -O /root/ZenithProxy-launcher-linux-amd64.zip \
    https://github.com/rfresh2/ZenithProxy/releases/download/launcher-v3/ZenithProxy-launcher-linux-amd64.zip && \
    unzip -o /root/ZenithProxy-launcher-linux-amd64.zip -d /root/ && \
    rm -f /root/ZenithProxy-launcher-linux-amd64.zip

RUN \
    mkdir -p /root/plugins && \
    curl -L -o /root/plugins/ZenithProxyWebAPI-1.0.5.jar \
    https://github.com/rfresh2/ZenithProxyWebAPI/releases/download/1.0.5/ZenithProxyWebAPI-1.0.5.jar

COPY run.sh /root/run.sh

RUN chmod +x /root/run.sh

EXPOSE 8080

CMD ["/root/run.sh"]
