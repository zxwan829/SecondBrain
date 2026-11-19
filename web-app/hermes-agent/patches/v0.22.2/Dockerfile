# Minimal overlay on the exact official v0.22.2 linux/amd64 image.
# Build context must contain agent/tool_executor.py from the pinned source
# after applying pre-tool-hook-fail-closed.patch.
FROM nousresearch/hermes-agent@sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05

ARG SB_HERMES_SOURCE_COMMIT
ARG SB_HERMES_PATCH_SHA256

LABEL org.opencontainers.image.version="0.22.2" \
      org.opencontainers.image.base.name="nousresearch/hermes-agent" \
      org.opencontainers.image.base.digest="sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05" \
      io.secondbrain.hermes.source-commit="${SB_HERMES_SOURCE_COMMIT}" \
      io.secondbrain.hermes.patch-sha256="${SB_HERMES_PATCH_SHA256}"

COPY agent/tool_executor.py /opt/hermes/agent/tool_executor.py
COPY gateway/platforms/weixin.py /opt/hermes/gateway/platforms/weixin.py
COPY weixin-inbox/ /opt/hermes/plugins/secondbrain-weixin-inbox/
COPY d078-guard/ /opt/hermes/plugins/secondbrain-d078-guard/
