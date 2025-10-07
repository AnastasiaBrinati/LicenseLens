FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

CMD ["streamlit", "run", "dash.py", "--server.port=8501", "--server.address=0.0.0.0"]