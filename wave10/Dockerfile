FROM mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27

USER root
WORKDIR /opt/od3b

RUN npm init -y     && npm install --save-exact --ignore-scripts --no-audit --no-fund playwright@1.63.0     && cp "$(readlink -f "$(command -v node)")" /opt/od3b/node     && chmod 0555 /opt/od3b/node

COPY live_canary.mjs /opt/od3b/live_canary.mjs
COPY post_stop_probe.mjs /opt/od3b/post_stop_probe.mjs

RUN groupadd --gid 1500 od3b     && useradd --uid 1500 --gid 1500 --create-home --shell /usr/sbin/nologin od3b

ENV HOME=/tmp/od3b-home
USER 1500:1500
WORKDIR /tmp
