FROM python:3.13-slim
WORKDIR /app
COPY services/selector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/selector/app ./app
CMD ["python", "-m", "app.main"]
