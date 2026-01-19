FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt-get update && \
    apt-get install -y \
    python3 python3-pip python3-venv python3-pexpect \
    unzip wget curl bash ca-certificates tzdata && \
    ln -fs /usr/share/zoneinfo/$TZ /etc/localtime && \
    rm -rf /var/lib/apt/lists/*

RUN wget -O /root/ZenithProxy-launcher-linux-amd64.zip \
    https://github.com/rfresh2/ZenithProxy/releases/download/launcher-v3/ZenithProxy-launcher-linux-amd64.zip && \
    unzip -o /root/ZenithProxy-launcher-linux-amd64.zip -d /root/ && \
    rm -f /root/ZenithProxy-launcher-linux-amd64.zip && \
    chmod +x /root/launch

RUN mkdir -p /root/plugins && \
    mkdir -p /root/plugins/config && \
    curl -L -o /root/plugins/ZenithProxyWebAPI-1.0.5.jar \
    https://github.com/rfresh2/ZenithProxyWebAPI/releases/download/1.0.5/ZenithProxyWebAPI-1.0.5.jar

COPY web-api.json /root/plugins/config/web-api.json

COPY run.sh /root/run.sh
RUN chmod +x /root/run.sh

COPY requirements.txt /root/requirements.txt
COPY zenith_setup.py /root/zenith_setup.py
COPY launch_controller.py /root/launch_controller.py

RUN \
    python3 -m venv /root/.venv && \
    /root/.venv/bin/pip install -r /root/requirements.txt && \
    /root/.venv/bin/python3 /root/zenith_setup.py

EXPOSE 8080

CMD ["/root/run.sh"]
