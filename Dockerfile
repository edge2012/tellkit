FROM python:3.12-slim
# Debian's GPL-enabled ffmpeg includes libx264. An LGPL-only build may fail
# with Unknown encoder 'libx264'; ffmpeg binaries are not bundled here.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/tellkit
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python", "demo/run.py"]
