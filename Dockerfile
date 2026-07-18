FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt pyproject.toml ./
COPY sdk/python ./sdk/python
COPY bank_api ./bank_api

RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/app/sdk/python:/app
ENV CHECKOUT_BANK_HOST=0.0.0.0
ENV CHECKOUT_BANK_PORT=8090
ENV CHECKOUT_BANK_DB=/data/checkout_bank.db

EXPOSE 8090

CMD ["python", "-m", "uvicorn", "bank_api.server:app", "--host", "0.0.0.0", "--port", "8090"]
