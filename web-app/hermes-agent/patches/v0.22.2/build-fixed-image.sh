#!/usr/bin/env bash
set -euo pipefail

source_checkout=${1:?usage: build-fixed-image.sh HERMES_SOURCE_CHECKOUT IMAGE_TAG}
image_tag=${2:?usage: build-fixed-image.sh HERMES_SOURCE_CHECKOUT IMAGE_TAG}
expected_commit=d923a5eb487a17c0a68801bba9ef0f56c81040a8
script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
patch_file="$script_dir/pre-tool-hook-fail-closed.patch"
media_patch_file="$script_dir/weixin-media-download-budget.patch"
dockerfile="$script_dir/Dockerfile"
weixin_plugin_dir="$script_dir/../../weixin-inbox"
d078_plugin_dir="$script_dir/../../d078-guard"

actual_commit=$(git -C "$source_checkout" rev-parse HEAD)
if [[ "$actual_commit" != "$expected_commit" ]]; then
    printf 'Expected Hermes source %s, got %s\n' "$expected_commit" "$actual_commit" >&2
    exit 2
fi
if [[ -n "$(git -C "$source_checkout" status --porcelain)" ]]; then
    echo "Hermes source checkout must be clean before building." >&2
    exit 2
fi

patch_sha=$(python3 -c 'import hashlib,pathlib,sys; h=hashlib.sha256(); [h.update(part) for path in sys.argv[1:] for part in (pathlib.Path(path).name.encode(), b"\0", pathlib.Path(path).read_bytes(), b"\0")]; print(h.hexdigest())' "$patch_file" "$media_patch_file" "$weixin_plugin_dir/__init__.py" "$weixin_plugin_dir/plugin.yaml" "$d078_plugin_dir/__init__.py" "$d078_plugin_dir/plugin.yaml")
build_root=$(mktemp -d "${TMPDIR:-/tmp}/secondbrain-hermes-v0222-build.XXXXXX")
cleanup() {
    rm -rf "$build_root"
}
trap cleanup EXIT

mkdir -p "$build_root/source" "$build_root/context/agent" "$build_root/context/gateway/platforms" "$build_root/context/weixin-inbox" "$build_root/context/d078-guard"
git -C "$source_checkout" archive "$expected_commit" | tar -x -C "$build_root/source"
git -C "$build_root/source" apply --unidiff-zero "$patch_file"
git -C "$build_root/source" apply --unidiff-zero "$media_patch_file"
cp "$build_root/source/agent/tool_executor.py" "$build_root/context/agent/tool_executor.py"
cp "$build_root/source/gateway/platforms/weixin.py" "$build_root/context/gateway/platforms/weixin.py"
cp "$weixin_plugin_dir/__init__.py" "$build_root/context/weixin-inbox/__init__.py"
cp "$weixin_plugin_dir/plugin.yaml" "$build_root/context/weixin-inbox/plugin.yaml"
cp "$d078_plugin_dir/__init__.py" "$build_root/context/d078-guard/__init__.py"
cp "$d078_plugin_dir/plugin.yaml" "$build_root/context/d078-guard/plugin.yaml"
cp "$dockerfile" "$build_root/context/Dockerfile"

docker build \
    --platform linux/amd64 \
    --network=none \
    --memory=2g \
    --cpuset-cpus=0,1 \
    --build-arg "SB_HERMES_SOURCE_COMMIT=$expected_commit" \
    --build-arg "SB_HERMES_PATCH_SHA256=$patch_sha" \
    --tag "$image_tag" \
    "$build_root/context"

printf 'image_tag=%s\nsource_commit=%s\npatch_sha256=%s\n' \
    "$image_tag" "$expected_commit" "$patch_sha"
