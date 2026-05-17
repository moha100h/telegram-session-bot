FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Install main requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install instagrapi separately (isolated from aiogram pydantic)
RUN pip install --no-cache-dir \
    "pydantic==1.10.21" \
    "instagrapi==1.6.4" \
    --no-deps

# Install instagrapi's own deps manually (compatible versions)
RUN pip install --no-cache-dir \
    "requests>=2.25.1" \
    "urllib3>=1.26.0" \
    "Pillow>=9.0.0" \
    "moviepy>=1.0.3" \
    "tqdm>=4.60.0" \
    "pyotp>=2.6.0" \
    "PySocks>=1.7.1" \
    "pycryptodomex>=3.9.4" \
    "pycountry>=22.3.5" \
    "orjson>=3.6.4" \
    "brotli>=1.0.9" \
    "pydantic-settings>=2.0.0" \
    || true

COPY . .

RUN mkdir -p /app/sessions /app/data /app/data/ig_sessions

CMD ["python", "main.py"]
