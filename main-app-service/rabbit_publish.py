import pika

class Publisher:
    def __init__(self, exchange_name='documentInfo'):
        # Открываем соединение
        rabbitCredentials = pika.PlainCredentials('module', 'Lthmvbot2022')
        self.connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq.com',
                                                                            5672,
                                                                            '/', rabbitCredentials))
        self.channel = self.connection.channel()

        # Объявляем exchange один раз
        self.channel.exchange_declare(exchange=exchange_name, exchange_type='fanout')

    def send_message(self, message):
        # Отправляем сообщение в exchange
        self.channel.basic_publish(exchange='documentInfo', routing_key='', body=message)
        print(f" [x] Sent: {message}")

    def close(self):
        # Закрываем канал и соединение
        self.channel.close()
        self.connection.close()
