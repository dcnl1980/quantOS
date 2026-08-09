FROM python:3.12-slim
WORKDIR /app
COPY packages/quant /app/packages/quant
COPY services/api /app/services/api
RUN pip install --no-cache-dir -r /app/services/api/requirements.txt
ENV PYTHONPATH=/app/packages/quant:/app/services/api
WORKDIR /app/services/api
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
