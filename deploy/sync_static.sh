#!/usr/bin/env bash
# 把 repo 里的静态文件（HTML / SVG / PNG / 数据 JSON）同步到 Nginx webroot。
# 改完代码 git pull 之后跑一次即可。

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/cry/repo}"
WWW_DIR="${WWW_DIR:-/var/www/cry}"

mkdir -p "$WWW_DIR/data"

# HTML / icon / manifest
cp "$REPO_DIR"/*.html "$WWW_DIR/" 2>/dev/null || true
cp "$REPO_DIR"/*.svg "$WWW_DIR/" 2>/dev/null || true
cp "$REPO_DIR"/*.png "$WWW_DIR/" 2>/dev/null || true
cp "$REPO_DIR"/*-manifest.json "$WWW_DIR/" 2>/dev/null || true

# 数据文件（首次部署时把 repo 自带的数据也 seed 过去）
cp -r "$REPO_DIR"/data/. "$WWW_DIR/data/" 2>/dev/null || true

chown -R www-data:www-data "$WWW_DIR"
echo "synced to $WWW_DIR"
