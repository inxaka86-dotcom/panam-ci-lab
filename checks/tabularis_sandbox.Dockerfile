FROM ubuntu:24.04

# Public, disposable CI test runtime only. The image contains no PANAM files.
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      python3 libssl3t64 libdbus-1-3 libgcc-s1 ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /app /work

ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /work
USER 65532:65532
