#!/usr/bin/env bash
# Install BotGeneralCalendar on Ubuntu: venv, deps, systemd unit.
# Run on the SERVER from the repo tree, as root:
#   cd BotGeneralCalendar/deploy/ubuntu && sudo ./install.sh
#
# Optional env:
#   INSTALL_DIR=/opt/bot-general-calendar
#   SERVICE_USER=botgencal

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/bot-general-calendar}"
SERVICE_USER="${SERVICE_USER:-botgencal}"
SERVICE_NAME="bot-general-calendar"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# BotGeneralCalendar/ (parent of deploy/)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ "${EUID:-0}" -ne 0 ]]; then
  echo "Запусти от root: sudo $0" >&2
  exit 1
fi

if [[ ! -f "$PROJECT_ROOT/bot.py" ]] || [[ ! -f "$PROJECT_ROOT/requirements.txt" ]]; then
  echo "Не найден bot.py рядом с deploy/ubuntu (ожидается каталог BotGeneralCalendar)." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y python3 python3-venv python3-pip rsync

mkdir -p "$INSTALL_DIR"

# Sync code; не трогаем существующий .env на сервере (его нет в репозитории)
rsync -a \
  --exclude '.git/' \
  --exclude 'venv/' \
  --exclude '__pycache__/' \
  --exclude '.env' \
  "$PROJECT_ROOT/" "$INSTALL_DIR/"

if ! id -u "$SERVICE_USER" &>/dev/null; then
  useradd --system \
    --home "$INSTALL_DIR" \
    --shell /usr/sbin/nologin \
    "$SERVICE_USER"
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
if [[ -f "$INSTALL_DIR/.env" ]]; then
  chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/.env"
  chmod 600 "$INSTALL_DIR/.env"
fi

if [[ ! -x "$INSTALL_DIR/venv/bin/python" ]]; then
  sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
fi
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

TMP_UNIT="$(mktemp)"
sed \
  -e "s|@@INSTALL_DIR@@|$INSTALL_DIR|g" \
  -e "s|@@SERVICE_USER@@|$SERVICE_USER|g" \
  "$SCRIPT_DIR/bot-general-calendar.service" >"$TMP_UNIT"
install -m 0644 "$TMP_UNIT" "/etc/systemd/system/${SERVICE_NAME}.service"
rm -f "$TMP_UNIT"

systemctl daemon-reload

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  systemctl disable "${SERVICE_NAME}.service" 2>/dev/null || true
  echo ""
  echo "Внимание: нет файла $INSTALL_DIR/.env — сервис не включаю и не запускаю."
  echo "Скопируй .env на сервер (chmod 600), затем снова:"
  echo "  sudo $0"
  echo "или: sudo systemctl enable --now ${SERVICE_NAME}.service"
  echo ""
  exit 0
fi

systemctl enable "${SERVICE_NAME}.service"
systemctl restart "${SERVICE_NAME}.service" || true
systemctl --no-pager -l status "${SERVICE_NAME}.service" || true

echo ""
echo "Готово. Логи: journalctl -u ${SERVICE_NAME}.service -f"
