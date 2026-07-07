FROM python:3.13-slim
WORKDIR /app
COPY services/bereiter/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/bereiter/app ./app
CMD ["python", "-m", "app.main"]
