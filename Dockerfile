#FROM ubuntu:latest
#LABEL authors="erikm"
#
#ENTRYPOINT ["top", "-b"]

FROM python:3.13.3-slim
WORKDIR /app

# Install iproute2 for 'tc' (Traffic Control) and ethtool for disabling NIC
# segmentation offloads (GSO/TSO/GRO) during pcap capture -- without this the
# sibling veth delivers multi-MB GSO super-frames and per-segment header
# overhead is lost from the capture.
RUN apt-get update && \
    apt-get install -y iproute2 ethtool && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1