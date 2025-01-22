# Используем официальный образ Python 3.12
FROM python:3.12-slim

# Установка утилит iproute2 и iptables для Debian, если нужно
#RUN apt-get update && apt-get install -y iputils-ping iproute2 iptables sudo

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл зависимостей в контейнер
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы приложения в контейнер
COPY . .

# Указываем команду для запуска приложения
CMD ["python", "app-consumer-uploader.py"]
