FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码 (CBOE data source) 
COPY . .

# 创建缓存目录
RUN mkdir -p .cache

EXPOSE 8000

CMD ["python", "run.py"]
