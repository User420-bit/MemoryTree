# Gunicorn-Konfiguration für Memory Tree (Pi Zero 2 W optimiert)
# Wird von Docker verwendet: gunicorn -c gunicorn.conf.py main:app

import multiprocessing

# 1 Worker: SQLite + 512 MB RAM + 2 User = mehr als ausreichend
workers = 1
worker_class = "uvicorn.workers.UvicornWorker"

# Binding — Caddy verbindet sich hierhin
bind = "0.0.0.0:8000"

# Timeouts (großzügig für Pi-Hardware und Bild-Uploads)
timeout = 120
graceful_timeout = 30
keepalive = 5

# Worker nach N Requests neustarten (Schutz gegen Memory-Leaks auf Pi)
max_requests = 1000
max_requests_jitter = 50

# Logging auf stdout/stderr für docker logs
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Graceful Shutdown
preload_app = False

# Tmp-Verzeichnis (wichtig für ARM/Docker)
tmp_upload_dir = "/tmp"
