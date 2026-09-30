FROM nvcr.io/nvidia/base/ubuntu:24.04@sha256:c280ee89f8bfcbdaba6179ad4347f60c509e841cbe63eb93002f01bf70e0819c

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       python3 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1500 sandbox \
    && useradd --uid 1500 --gid 1500 --create-home --shell /bin/bash sandbox

USER 1500:1500
WORKDIR /tmp
