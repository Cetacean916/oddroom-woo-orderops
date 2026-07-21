FROM node@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS dependencies
WORKDIR /build
COPY packaging/common/task-runner-deps/package.json packaging/common/task-runner-deps/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund

FROM n8nio/runners@sha256:d890fe221de44d75e1900eaf83f4499ad63503bfcc97cb04f0abfe5bc48bc0a6
LABEL io.pf07.task-runner.contract="n8n-2.25.7-json-bigint-1.0.0-pf07v1"
USER root
COPY --from=dependencies --chown=root:root /build/node_modules/json-bigint /opt/runners/task-runner-javascript/node_modules/json-bigint
COPY --from=dependencies --chown=root:root /build/node_modules/bignumber.js /opt/runners/task-runner-javascript/node_modules/bignumber.js
COPY --chown=root:root packaging/common/n8n-task-runners.json /etc/n8n-task-runners.json
RUN chmod 0644 /etc/n8n-task-runners.json && chmod -R a=rX,go-w \
    /opt/runners/task-runner-javascript/node_modules/json-bigint \
    /opt/runners/task-runner-javascript/node_modules/bignumber.js
USER runner
