FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# System dependencies: Tesseract OCR + Khmer lang pack, Poppler, LibreOffice, Khmer fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-khm \
    tesseract-ocr-eng \
    poppler-utils \
    libreoffice-nogpu \
    fonts-khmeros \
    fonts-noto-core \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    wget \
    unzip \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Install Google Noto Sans Khmer fonts
RUN mkdir -p /usr/share/fonts/truetype/noto-khmer \
    && wget -q "https://fonts.google.com/download?family=Noto%20Sans%20Khmer" -O /tmp/noto-khmer.zip \
    && unzip -q /tmp/noto-khmer.zip -d /usr/share/fonts/truetype/noto-khmer/ \
    && fc-cache -f \
    && rm -f /tmp/noto-khmer.zip

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create temp directory for uploads
RUN mkdir -p /app/temp

EXPOSE 8000 8501

# Default command: launch FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
