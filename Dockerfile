# CityScope — single-container deploy (backend serves the PWA frontend too).
FROM python:3.12-slim

WORKDIR /app

# install deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# app code (includes cityscope/web with the PWA)
COPY cityscope ./cityscope

# Hosts inject $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Bind to 0.0.0.0 so the platform can route to it. Shell form so $PORT expands.
CMD uvicorn cityscope.api.app:app --host 0.0.0.0 --port ${PORT}
