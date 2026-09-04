FROM node:22-bookworm

# The base image already owns uid/gid 1000 as user `node`. Reuse it so the
# bind-mounted workspace stays writable; override the args when the host user
# is not 1000:1000.
ARG UID=1000
ARG GID=1000
RUN if [ "$GID" != "1000" ]; then groupmod -g "$GID" node; fi \
 && if [ "$UID" != "1000" ]; then usermod -u "$UID" -g "$GID" node; fi \
 && chown -R "$UID:$GID" /home/node

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER node
ENV NPM_CONFIG_PREFIX=/home/node/.npm-global
ENV PATH=/home/node/.local/bin:/home/node/.npm-global/bin:$PATH
RUN npm install -g @anthropic-ai/claude-code \
 && curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
WORKDIR /workspace

ENTRYPOINT ["entrypoint.sh"]
