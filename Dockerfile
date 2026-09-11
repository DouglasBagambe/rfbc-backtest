FROM python:3.13-slim
WORKDIR /app
COPY monitor/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/monitor
CMD ["python", "monitor/webapp.py"]
