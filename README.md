# Розгортання Image Processor на Synology NAS

## Архітектура деплою

```
     PC                Git repo (GitHub)              Synology NAS
  ┌──────┐   1. push    ┌──────────────┐   3. clone   ┌──────────────┐
  │      │ ──────────►  │              │ ◄──────────  │              │
  │  PC  │              │   GitHub     │              │   Synology   │
  │      │ ──────────────────────────────────────────►│              │
  └──────┘   2. ssh (trigger deploy)                  └──────┬───────┘
                                                             │ docker
                                                             ▼
                                                    ┌──────────────┐
                                                    │  Container   │
                                                    │  build+run   │
                                                    └──────────────┘
```

---

## Швидкий деплой (одна команда)

Після початкового налаштування (див. нижче) весь деплой виконується однією командою:

```powershell
# Windows (PowerShell)
.\deploy.ps1

# або з явним repo
.\deploy.ps1 -GitRepo "https://github.com/youruser/image_processor.git"
```

```bash
# Linux / macOS / Git Bash
bash deploy.sh
```

Скрипт автоматично:
1. Коммітить і пушить зміни в GitHub
2. Підключається по SSH до Synology
3. Клонує (або оновлює) репозиторій
4. Збирає Docker образ
5. Перезапускає контейнер

---

## Вимоги

- **Synology NAS** з процесором Intel/AMD (x86-64). ARM моделі **не підтримуються** (ODBC Driver 17 лише для x86-64).
- **Container Manager** (раніше — Docker) встановлений з Package Center.
- **Git** встановлений на Synology (Package Center або Entware).
- **Tailscale** — встановлений на Synology і підключений до тієї ж мережі, що й SQL Server.
- **SSH** доступ до Synology (увімкнути в Control Panel → Terminal & SNMP).

---

## Початкове налаштування

### Крок 0. Створити GitHub репозиторій

1. Створіть **приватний** репозиторій на GitHub (наприклад `image_processor`)
2. На вашому PC, в папці проєкту:

```powershell
cd C:\Users\Bohdan-PC\Desktop\image_processor
git init
git remote add origin https://github.com/YOURUSER/image_processor.git
git add -A
git commit -m "initial commit"
git branch -M main
git push -u origin main
```

### Крок 1. Налаштувати SSH доступ до Synology

1. Увімкніть SSH на Synology: **Control Panel → Terminal & SNMP → Enable SSH**
2. На PC згенеруйте SSH ключ (якщо ще немає):

```powershell
ssh-keygen -t ed25519
```

3. Скопіюйте ключ на Synology:

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh admin@100.119.20.23 "mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys"
```

4. Перевірте підключення (без пароля):

```powershell
ssh admin@100.119.20.23 "echo OK"
```

### Крок 2. Встановити Git на Synology

Підключіться по SSH та встановіть Git:

```bash
# Через Package Center (рекомендовано):
# Встановіть "Git" або "Git Server" з Package Center UI

# Або через opkg (якщо встановлений Entware):
sudo opkg install git
```

Перевірте:
```bash
git --version
```

### Крок 3. Налаштувати deploy.ps1

Відкрийте `deploy.ps1` і перевірте параметри:

```powershell
$SynologyUser = "admin"              # ваш SSH юзер
$SynologyHost = "100.119.20.23"      # IP Synology (Tailscale або LAN)
$RemoteDir = "/volume1/docker/image_processor"
```

### Крок 4. Перший деплой

```powershell
.\deploy.ps1
```

Після першого деплою — відредагуйте `.env` на Synology:

```bash
ssh admin@100.119.20.23
nano /volume1/docker/image_processor/.env
```

Заповніть реальні значення:
```env
OPENAI_API_KEY=sk-your-real-key
OPENAI_MODEL=gpt-4.1
FLASK_ENV=production
SECRET_KEY=випадковий-рядок-тут
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_SERVER=100.119.20.23,1433
DB_NAME=ProcessedMedia
DB_USER=SA
DB_PASSWORD=nP2ks4!00b
MEDIA_ROOT=/media
```

> **MEDIA_ROOT=/media** — обов'язково! Вказує додатку працювати у режимі Synology (веб-браузер папок замість Windows діалогу).

---

## Налаштувати volume mounts

Відкрийте `docker-compose.synology.yml` і вкажіть ваші спільні папки Synology:

```yaml
volumes:
  - ./data/uploads:/app/uploads
  - ./data/processed:/app/processed
  # Монтуємо спільні папки Synology → в контейнер під /media/
  - /volume1/photo:/media/photo:ro
  - /volume1/homes/admin/Photos:/media/my-photos:ro
  # Додайте скільки потрібно
```

Кожна папка з фото, яку ви хочете обробляти, повинна бути змонтована під `/media/`.

---

## Оновлення (щоденний workflow)

Після будь-яких змін у коді на PC:

```powershell
.\deploy.ps1
```

Це все! Скрипт сам пушить, підключається до Synology, оновлює код і перезапускає контейнер.

---

## Tailscale: доступ до SQL Server

### Варіант A — `network_mode: host` (рекомендовано)
Контейнер використовує мережевий стек Synology, включаючи Tailscale. Нічого додатково налаштовувати не потрібно — просто вкажіть Tailscale IP у `DB_SERVER`.

### Варіант B — Bridge мережа
1. У `docker-compose.synology.yml` закоментуйте `network_mode: host`.
2. Розкоментуйте `ports` та `extra_hosts`.
3. Переконайтеся, що маршрутизація Tailscale дозволяє контейнеру доступ до SQL Server.

---

## Корисні команди

```bash
# SSH на Synology
ssh admin@100.119.20.23

# Переглянути логи контейнера
cd /volume1/docker/image_processor
docker-compose -f docker-compose.synology.yml logs -f

# Перезапустити
docker-compose -f docker-compose.synology.yml restart

# Зупинити
docker-compose -f docker-compose.synology.yml down

# Перезібрати вручну (без deploy.ps1)
docker-compose -f docker-compose.synology.yml up -d --build
```

---

## Вирішення проблем

| Проблема | Рішення |
|----------|---------|
| `git: command not found` на Synology | Встановіть Git через Package Center або Entware |
| `Permission denied (publickey)` | Налаштуйте SSH ключі (Крок 1) |
| Не бачу папки у браузері | Перевірте volume mounts — папки мають бути під `/media/` |
| Помилка з'єднання з SQL Server | Переконайтеся, що Tailscale працює і `DB_SERVER` вірний |
| `ODBC Driver 17` не знайдено | NAS повинен бути на Intel/AMD процесорі (не ARM) |
| Порт 5050 зайнятий | Змініть порт у Dockerfile та docker-compose |
| `.env` не знайдено після деплою | Скрипт створить шаблон — відредагуйте його на Synology |
