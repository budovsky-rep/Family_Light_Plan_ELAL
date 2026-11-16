FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    ELAL_LIVE_FETCH_ENABLED=1 \
    VACATION_PLANNER_DB_PATH=/app/data/vacation_planner.db

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
RUN mkdir -p /app/data && chmod +x /app/plan-vacation

EXPOSE 8080

CMD ["python3", "-m", "backend.app.main"]
