# HF Docker Space (읽기 전용 UI)
FROM python:3.12-slim
WORKDIR /app
ENV CACHE_BACKEND=hf_dataset
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install --no-cache-dir -e .
EXPOSE 7860
CMD ["python", "app.py"]
