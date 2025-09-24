# 1. Base image leggera con Python
FROM python:3.11-slim

# 2. Variabili ambiente per Streamlit
ENV PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# 3. Set working directory
WORKDIR /app

# 4. Copia e installa dipendenze
COPY config/config.yaml /config/config.yaml
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copia tutto il codice della dashboard
COPY . .

# 6. Espone la porta Streamlit
EXPOSE 8501

# 7. Comando di avvio
CMD ["streamlit", "run", "dash.py"]