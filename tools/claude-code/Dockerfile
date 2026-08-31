FROM node:22-bookworm
RUN useradd -m dev
USER dev
ENV NPM_CONFIG_PREFIX=/home/dev/.npm-global
ENV PATH=/home/dev/.npm-global/bin:$PATH
RUN npm install -g @anthropic-ai/claude-code
WORKDIR /workspace
