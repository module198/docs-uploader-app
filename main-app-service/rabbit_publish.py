import pika
from utils import rabbit_user, rabbit_pass, rabbit_host, logger

class Publisher:
    def __init__(self, exchange_name='documentInfo'):
        # Открываем соединение
        rabbitCredentials = pika.PlainCredentials(rabbit_user, rabbit_pass)
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(rabbit_host,
                                                                            5672,
                                                                            '/', rabbitCredentials))
        self.channel = self.connection.channel()

        # Объявляем exchange один раз
        self.channel.exchange_declare(exchange=exchange_name, exchange_type='fanout')

    def send_message(self, message):
        # Отправляем сообщение в exchange
        self.channel.basic_publish(exchange='documentInfo', routing_key='', body=message)
        logger.info(f'Sent to RabbitMQ: {message}')

    def close(self):
        # Закрываем канал и соединение
        self.channel.close()
        self.connection.close()
