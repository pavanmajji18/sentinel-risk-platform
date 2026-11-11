# ---- builder stage ----
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- runtime stage ----
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY main.py .
# Model artifacts are mounted at runtime — not baked into image
# docker run -v ./model:/app/model ...
RUN adduser --disabled-password --gecos "" appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
