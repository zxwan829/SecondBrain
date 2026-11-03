#!/bin/zsh
set -e
cd "$(dirname "$0")"
echo "VNext 预览地址：http://127.0.0.1:4182/vnext.html"
npm run dev:vnext
