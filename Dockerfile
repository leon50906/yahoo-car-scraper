# 使用輕量級的 Python 3.9
FROM python:3.9-slim

# 設定工作目錄
WORKDIR /app

# 設定時區為台北 (避免抓到的時間怪怪的)
ENV TZ=Asia/Taipei

# 複製檔案進去
COPY requirements.txt .
COPY app.py .

# 安裝套件
RUN pip install --no-cache-dir -r requirements.txt

# 開放 5000 port
EXPOSE 5000

# 啟動指令
CMD ["python", "app.py"]