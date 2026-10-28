FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY servicos/ servicos/
COPY documentos/ documentos/
EXPOSE 8001
CMD ["uvicorn", "servicos.ingestao.app:app", "--host", "0.0.0.0", "--port", "8001"]
