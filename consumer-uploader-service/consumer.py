import pika
import json
import time
from google_utils import files_uploading
from utils import rabbit_user, rabbit_pass, rabbit_host, rabbit_port, logger

class Consumer:
    def __init__(self, exchange_name='documentInfo', queue_name='documentQueue'):
        self.connection = None
        self.channel = None
        self.exchange_name = exchange_name
        self.queue_name = queue_name

        # Пытаемся подключиться к RabbitMQ с таймаутом
        self.connect_to_rabbitmq()

    def connect_to_rabbitmq(self):
        """Подключение к RabbitMQ с таймаутом и повторными попытками."""
        attempt = 0
        max_attempts = 60  # Максимум 60 попыток (по 1 минуте)

        while attempt < max_attempts:
            try:
                rabbit_credentials = pika.PlainCredentials(rabbit_user, rabbit_pass)
                logger.info('Connecting to RabbitMQ: {}'.format(rabbit_host), rabbit_user, rabbit_pass)
                self.connection = pika.BlockingConnection(
                    pika.ConnectionParameters(rabbit_host, 5672, '/', rabbit_credentials)
                )
                self.channel = self.connection.channel()
                logger.info('Connected to RabbitMQ: {}'.format(rabbit_host))
                # Объявляем exchange
                self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='fanout')
                # Создаём очередь
                self.channel.queue_declare(queue=self.queue_name, durable=True)
                # Привязываем очередь к exchange
                self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name)
                break
            except pika.exceptions.AMQPConnectionError as e:
                attempt += 1
                logger.exception(f"Attempt {attempt}/{max_attempts}: Failed to connect to RabbitMQ. Retrying in 60 seconds...")
                time.sleep(60)  # Ждём 1 минуту перед повторной попыткой
        else:
            logger.error("Failed to connect to RabbitMQ after multiple attempts.")
            # Вместо того чтобы выбрасывать исключение, можно просто продолжить попытки
            # или начать слушать очередь, если удалось подключиться хотя бы к другому экземпляру.
            # Здесь можно внедрить дополнительную логику обработки ошибок (например, логирование).

    def callback(self, ch, method, properties, body):
        form_data = json.loads(body.decode())
        # Загружаем файлы на Google Диск
        logger.info(f'Начинаю загрузку файлов на диск, {form_data}')
        files_uploading(form_data)
        # Сообщаем RabbitMQ, что сообщение обработано
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def start_consuming(self):
        """Начинаем прослушивание очереди"""
        if not self.connection or not self.channel:
            logger.warning("No connection to RabbitMQ, exiting consumer...")
            return
        logger.info('Waiting for messages')
        self.channel.basic_consume(queue=self.queue_name, on_message_callback=self.callback)
        self.channel.start_consuming()

    def close(self):
        """Закрытие канала и соединения"""
        if self.channel and self.connection:
            self.channel.close()
            self.connection.close()
        else:
            logger.info("No open connection or channel to close.")
