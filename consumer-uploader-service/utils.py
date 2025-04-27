import requests, json
from google.oauth2.credentials import Credentials
import os
from dotenv import load_dotenv
import logging

# Путь к корневой директории сервиса
BASE_DIR = os.getenv("BASE_DIR", os.path.abspath(os.path.dirname(__file__)))
# Путь к папке shared
SHARED_DIR = os.getenv("SHARED_DIR", os.path.abspath(os.path.join(BASE_DIR, '..', 'shared')))
# Путь к логам
LOG_PATH = os.path.join(SHARED_DIR, 'logs', 'app.log')
# Путь к файлу с секретами
CLIENT_SECRETS_FILE = os.path.join(SHARED_DIR, 'creds', 'client_secret.json')
# Путь к .env файлу внутри папки creds
# dotenv_path = os.path.join(BASE_DIR, '..', '.env')
dotenv_path = '/app/.env'
# Путь к папке для временного хранилища файлов для загрузки
UPLOAD_FOLDER = os.path.join(SHARED_DIR, 'uploads')

# Загрузить переменные из .env
load_dotenv(dotenv_path)
rabbit_user = os.getenv('RABBITMQ_USER')
rabbit_pass = os.getenv('RABBITMQ_PASS')
rabbit_host = os.getenv('RABBITMQ_HOST')
rabbit_port = os.getenv('RABBITMQ_PORT')

# Настройка конфигурации логирования
logging.basicConfig(
    level=logging.INFO,  # Уровень логирования (можно выбрать: DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Формат сообщения
    handlers=[
        logging.StreamHandler(),  # Вывод логов в консоль
        logging.FileHandler(LOG_PATH)  # Запись логов в файл 'app.log'
    ]
)
logger = logging.getLogger('consumer-uploader-service')

# Функция для получения данных пользователя через Google People API
def get_user_info(access_token):
    url = 'https://www.googleapis.com/oauth2/v3/userinfo'
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        user_data = response.json()
        email = user_data.get('email', '')
        return email
    else:
        print(f"Error getting user email: {response.status_code}")
        return None, None



# Класс для работы с учёткой и токенами
class UserAccount:
    def __init__(self, email):
        self.email = email
        # self.credentials_file = "../shared/creds/tokens.json"
        self.credentials_file = os.path.join(SHARED_DIR, 'creds', 'tokens.json')
        self.credentials = self.load_credentials()

    def load_credentials(self):
        """Загружает credentials из файла, если они существуют."""
        if os.path.exists(self.credentials_file):
            with open(self.credentials_file, 'r') as file:
                data = json.load(file)
                if self.email in data:
                    return Credentials(
                        token=data[self.email]["token"],
                        refresh_token=data[self.email].get("refresh_token"),
                        token_uri=data[self.email]["token_uri"],
                        client_id=data[self.email]["client_id"],
                        client_secret=data[self.email]["client_secret"],
                        scopes=data[self.email]["granted_scopes"]
                    )
        return None

    def save_credentials(self, credentials):
        """Сохраняет credentials в файл."""
        if os.path.exists(self.credentials_file):
            with open(self.credentials_file, 'r') as file:
                data = json.load(file)
        else:
            data = {}

        # Проверка существования записи конкретного юзера
        if self.email not in data:
            data[self.email] = {}

            # Предусматриваем кейс, если refresh токен есть в файле, но не пришёл с новыми credentials
            # (чтобы не перезаписать как None)
        if not data[self.email].get("token") or (data[self.email].get("token") and credentials.refresh_token):
            data[self.email] = {
                "token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "granted_scopes": credentials.granted_scopes
            }
        elif data[self.email].get("token"):
            data[self.email]["token"] = credentials.token

        with open(self.credentials_file, 'w') as file:
            json.dump(data, file, indent=4)

    def is_token_valid(self):
        """Проверяет валидность access токена."""
        if not self.credentials:
            return False

        url = f"https://www.googleapis.com/oauth2/v3/tokeninfo?access_token={self.credentials.token}"
        response = requests.get(url)

        if response.status_code == 200:
            return True
        return False

    def refresh_token(self):
        """Обновляет refresh_token, если он доступен."""
        if self.credentials and self.credentials.refresh_token:
            url = "https://oauth2.googleapis.com/token"
            data = {
                'client_id': self.credentials.client_id,
                'client_secret': self.credentials.client_secret,
                'refresh_token': self.credentials.refresh_token,
                'grant_type': 'refresh_token',
            }
            response = requests.post(url, data=data)

            if response.status_code == 200:
                new_credentials = response.json()
                # Создаем новый объект Credentials с обновлёнными токенами
                self.credentials = Credentials(
                    token=new_credentials['access_token'],
                    refresh_token=self.credentials.refresh_token,  # Сохраняем старый refresh_token
                    token_uri=self.credentials.token_uri,
                    client_id=self.credentials.client_id,
                    client_secret=self.credentials.client_secret,
                    scopes=self.credentials.scopes,
                )
                self.save_credentials(self.credentials)  # Сохраняем обновленные токены
                return True
        return False

    def credentials_to_dict(self):
        """Конвертирует объект credentials в dictionary"""
        if self.credentials:
            return {'token': self.credentials.token,
                    'refresh_token': self.credentials.refresh_token,
                    'token_uri': self.credentials.token_uri,
                    'client_id': self.credentials.client_id,
                    'client_secret': self.credentials.client_secret,
                    'granted_scopes': self.credentials.granted_scopes}


    def revoke_token(self):
        """Отзывает текущий токен."""
        revoke_url = "https://oauth2.googleapis.com/revoke"
        response = requests.post(revoke_url, params={'token': self.credentials.token})

        if response.status_code == 200:
            self.credentials = None  # Убираем токены из объекта
            return True
        return False


def delete_files_in_directory(directory_path):
    """
    Удаляет все файлы в указанной директории. Поддиректории не удаляются.

    :param directory_path: Путь к директории, в которой нужно удалить все файлы.
    :return: None
    """
    try:
        # Проверяем, существует ли указанная директория
        if not os.path.exists(directory_path):
            logger.warning(f"Директория {directory_path} не существует.")
            return

        # Перебираем все файлы в директории
        for filename in os.listdir(directory_path):
            file_path = os.path.join(directory_path, filename)
            # Проверяем, является ли объект файлом
            if os.path.isfile(file_path):
                os.remove(file_path)
                logger.info(f"Файл {filename} был удален из временного хранилища.")
            else:
                logger.warning(f"{filename} не является файлом, пропущено.")

    except Exception as e:
        logger.exception(f"Ошибка при удалении файлов из временного хранилища: {e}")