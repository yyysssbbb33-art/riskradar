# HF Docker Space (읽기 전용 UI). 컨테이너는 UID 1000(user)로 실행된다.
FROM python:3.12-slim

# HF Spaces 권장: user 생성 + 쓰기 가능한 HOME/캐시 지정
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    CACHE_BACKEND=hf_dataset

WORKDIR /app
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install --no-cache-dir -e .

USER user
EXPOSE 7860
CMD ["python", "app.py"]
