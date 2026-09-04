#!/usr/bin/env bash
# Evidence Copilot 桌面版安装脚本（OpenCode 风格）
# 用法: curl -fsSL https://raw.githubusercontent.com/LawrenceLiu2005/MedCopilot/main/scripts/install.sh | bash
set -euo pipefail

REPO="${EVIDENCE_COPILOT_REPO:-LawrenceLiu2005/MedCopilot}"
VERSION="${EVIDENCE_COPILOT_VERSION:-latest}"
INSTALL_DIR="${EVIDENCE_COPILOT_INSTALL_DIR:-$HOME/Applications}"

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

case "$ARCH" in
  arm64|aarch64) ARCH_TAG="arm64" ;;
  x86_64|amd64) ARCH_TAG="x64" ;;
  *) echo "不支持的架构: $ARCH" >&2; exit 1 ;;
esac

if [ "$OS" != "darwin" ]; then
  echo "当前 install.sh 首版仅支持 macOS；Windows 请从 GitHub Releases 下载 .exe。" >&2
  exit 1
fi

if [ "$VERSION" = "latest" ]; then
  URL="https://github.com/${REPO}/releases/latest/download/EvidenceCopilot-mac-${ARCH_TAG}.dmg"
else
  URL="https://github.com/${REPO}/releases/download/${VERSION}/EvidenceCopilot-mac-${ARCH_TAG}.dmg"
fi

TMP="$(mktemp -d)"
DMG="${TMP}/EvidenceCopilot.dmg"
echo "正在下载 Evidence Copilot…"
echo "  ${URL}"
curl -fsSL "$URL" -o "$DMG"

MOUNT="$(hdiutil attach -nobrowse -readonly "$DMG" | awk '/\/Volumes\// {print $3; exit}')"
cleanup() {
  hdiutil detach "$MOUNT" >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap cleanup EXIT

mkdir -p "$INSTALL_DIR"
APP_SRC="$(find "$MOUNT" -maxdepth 1 -name '*.app' | head -n 1)"
if [ -z "$APP_SRC" ]; then
  echo "在 DMG 中未找到 .app" >&2
  exit 1
fi

APP_NAME="$(basename "$APP_SRC")"
rm -rf "${INSTALL_DIR}/${APP_NAME}"
cp -R "$APP_SRC" "${INSTALL_DIR}/"
echo "已安装到 ${INSTALL_DIR}/${APP_NAME}"
echo "首次打开若提示未验证开发者，请在图标上右键 → 打开。"
