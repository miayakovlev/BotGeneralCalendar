# Развёртывание BotGeneralCalendar на Ubuntu (VM)

Бот работает в режиме **long polling** (исходящие HTTPS-запросы к Telegram и iCloud CalDAV). Входящие порты и веб-сервер **не нужны**.

---

## Требования к серверу

- **ОС**: Ubuntu 22.04 / 24.04 (или другой Debian-based).
- **Сеть**: исходящий доступ по **HTTPS (443)** к:
  - `api.telegram.org`
  - `caldav.icloud.com`
- **Ресурсы**: достаточно 1 vCPU, 512 MB–1 GB RAM.

---

## 1. Скопировать код на VM

### Вариант A — Git

```bash
ssh user@SERVER
git clone <URL_репозитория>
cd <репозиторий>/BotGeneralCalendar
```

### Вариант B — Rsync с локального компьютера

Из каталога, где лежит папка `BotGeneralCalendar` (например `TelegramBot`):

```bash
rsync -avz --exclude '.git' --exclude 'venv' --exclude '__pycache__' \
  BotGeneralCalendar/ user@SERVER:~/BotGeneralCalendar/
```

---

## 2. Файл секретов `.env`

Скрипт установки копирует код в **`/opt/bot-general-calendar`** и **не** подтягивает `.env` из репозитория (секреты только на сервере).

Скопируй локальный `.env` или создай файл на сервере по шаблону `.env.example`.

**Пример** (после первого успешного `install.sh` пользователь `botgencal` уже существует):

```bash
sudo mkdir -p /opt/bot-general-calendar
scp BotGeneralCalendar/.env user@SERVER:/tmp/bgc.env
ssh user@SERVER "sudo mv /tmp/bgc.env /opt/bot-general-calendar/.env && \
  sudo chown botgencal:botgencal /opt/bot-general-calendar/.env && \
  sudo chmod 600 /opt/bot-general-calendar/.env"
```

Если `.env` положили **до** первого запуска `install.sh`, после установки выполни:

```bash
sudo chown botgencal:botgencal /opt/bot-general-calendar/.env
sudo chmod 600 /opt/bot-general-calendar/.env
```

Файл должен быть **читаем пользователем сервиса** `botgencal` (бот читает `.env` из Python).

---

## 3. Установка: venv, зависимости, systemd

На **сервере**, из каталога с проектом:

```bash
cd ~/BotGeneralCalendar/deploy/ubuntu
sudo chmod +x install.sh
sudo ./install.sh
```

По умолчанию:

| Параметр | Значение |
|----------|----------|
| Каталог установки | `/opt/bot-general-calendar` |
| Пользователь сервиса | `botgencal` |
| Имя unit | `bot-general-calendar.service` |

Свои пути:

```bash
sudo INSTALL_DIR=/opt/мой-каталог SERVICE_USER=мой_юзер ./install.sh
```

Если **`/opt/.../.env` ещё нет**, скрипт поставит код и unit, но **не включит** автозапуск. После появления `.env` запусти установку снова:

```bash
sudo ./install.sh
```

или:

```bash
sudo systemctl enable --now bot-general-calendar.service
```

---

## 4. Проверка и логи

```bash
sudo systemctl status bot-general-calendar.service
journalctl -u bot-general-calendar.service -f
```

Перезапуск после правок конфига:

```bash
sudo systemctl restart bot-general-calendar.service
```

---

## 5. Обновление кода

Снова залей изменения (`git pull` или `rsync`), затем на сервере:

```bash
sudo ~/BotGeneralCalendar/deploy/ubuntu/install.sh
```

(путь к `install.sh` поправь под место, куда лежит репозиторий на VM).

---

## 6. Устранение неполадок

| Симптом | Что проверить |
|--------|----------------|
| `Conflict` / ошибки Telegram при polling | Не запущен ли тот же бот **в другом месте** с тем же токеном. |
| `ProxyError` / 403 | На сервере не должны мешать глобальные `HTTP_PROXY`/`HTTPS_PROXY` (в unit они обнуляются). |
| Ошибка CalDAV / календарь не найден | `ICLOUD*_CALENDAR_NAME` совпадает с именем в приложении «Календарь», app-password верный. |
| Бот не видит `.env` | Права `chown botgencal:botgencal` и `chmod 600`, путь `/opt/bot-general-calendar/.env`. |

---

## Файлы в репозитории

- `deploy/ubuntu/install.sh` — установка
- `deploy/ubuntu/bot-general-calendar.service` — шаблон unit (подставляется скриптом)
- `deploy/ubuntu/README.txt` — краткая копия шагов
