FROM python:3.12-slim

WORKDIR /app

# Dependencias primero: capa cacheada, no se reinstala al tocar código o CSS
RUN pip install --no-cache-dir flask beautifulsoup4 gunicorn

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir --no-deps .

EXPOSE 8113

CMD ["gunicorn", "--bind", "0.0.0.0:8113", "--workers", "2", \
     "--timeout", "60", "--access-logfile", "-", \
     "ducksforducks.app:app"]