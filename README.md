````md
# Project Setup

## Prerequisites
- Python 3.8+
- pip
- Homebrew (macOS only, for Redis)
- Git (optional)

---

## 1. Create Virtual Environment

```bash
python3 -m venv .venv
````

## 2. Activate Virtual Environment

### macOS / Linux

```bash
source .venv/bin/activate
```

### Windows (PowerShell)

```bash
.venv\Scripts\Activate.ps1
```

### Windows (CMD)

```bash
.venv\Scripts\activate.bat
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Install Playwright Browsers

```bash
python -m playwright install
```

---

## 5. Install and Start Redis

### macOS (Homebrew)

```bash
brew install redis
brew services start redis
```

### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install redis-server -y
sudo systemctl enable redis
sudo systemctl start redis
```

### Windows

Use Redis from WSL or install via:
[https://github.com/microsoftarchive/redis/releases](https://github.com/microsoftarchive/redis/releases)

---

## 6. Run the Project

```bash
python3 -m Scraper.main
```

---

## Notes

* Always activate the virtual environment before running commands.
* If Playwright fails, rerun:

  ```bash
  python -m playwright install
  ```
* Ensure Redis is running before starting the scraper.

```

If you want, I can also add:
- Docker setup
- Makefile / task runner
- One-line install script (`setup.sh`)
```
