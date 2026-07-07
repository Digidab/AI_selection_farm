FROM python:3.13-slim
WORKDIR /app
COPY services/trainer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/trainer/app ./app
CMD ["python", "-m", "app.main"]
