FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY servicos/ servicos/
EXPOSE 8002
CMD ["uvicorn", "servicos.recuperacao.app:app", "--host", "0.0.0.0", "--port", "8002"]
