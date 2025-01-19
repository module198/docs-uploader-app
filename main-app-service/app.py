import flask
from flask import Flask, redirect, url_for, session, request, render_template, flash
import google_auth_oauthlib.flow
from utils import *
import time
from datetime import datetime
from rabbit_publish import Publisher
import json
# import logging

'''
Пример логгирования:
logging.debug('Это сообщение уровня DEBUG')
logging.info('Это сообщение уровня INFO')
logging.warning('Это сообщение уровня WARNING')
logging.error('Это сообщение уровня ERROR')
logging.critical('Это сообщение уровня CRITICAL')
'''

# # Настройка конфигурации логирования
# logging.basicConfig(
#     level=logging.ERROR,  # Уровень логирования (можно выбрать: DEBUG, INFO, WARNING, ERROR, CRITICAL)
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Формат сообщения
#     handlers=[
#         logging.StreamHandler(),  # Вывод логов в консоль
#         logging.FileHandler(LOG_PATH)  # Запись логов в файл 'app.log'
#     ]
# )

app = Flask(__name__)
# Note: A secret key is included in the sample so that it works.
# If you use this code in your application, replace this with a truly secret
# key. See https://flask.palletsprojects.com/quickstart/#sessions.
app.secret_key = 'REPLACE ME - this value is here as a placeholder.'

# Указываем путь для временного сохранения файлов
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Создаём директорию, если её не существует
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
@app.route('/')
def index():
    user_account = UserAccount(session.get('email'))
    # Проверяем токен из файла на валидность
    if user_account.is_token_valid():
        # Если пользователь авторизован, перенаправляем на форму проверяем токен
        return redirect(url_for('form'))
    else:
        # Если пользователь не авторизован, перенаправляем на страницу логина
        print("Токен не валиден")
        # Если есть токены в файле, рефрешим их
        if user_account.credentials:
            user_account.refresh_token()
        return redirect(url_for('login'))


@app.route('/login')
def login():
    return render_template('login.html')  # Главная страница с кнопкой авторизации

@app.route('/authorize')
def authorize():
    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

    authorization_url, state = flow.authorization_url(
        # Enable offline access so that you can refresh an access token without
        # re-prompting the user for permission. Recommended for web server apps.
        access_type='offline',
        # Enable incremental authorization. Recommended as a best practice.
        include_granted_scopes='true')

    return flask.redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    authorization_response = flask.request.url
    flow.fetch_token(authorization_response=authorization_response)
    if not flow.credentials or not flow.credentials.valid:
        flash("Authorization failed.", "error")
        return flask.redirect('/')

    email = get_user_info(flow.credentials.token)
    user_account = UserAccount(email)
    user_account.save_credentials(flow.credentials) # Сохраняем credentials в файл
    user_account.credentials =  user_account.load_credentials()

    session['email'], session["credentials"] = user_account.email, user_account.credentials_to_dict()

    print(session)
    return flask.redirect('/form')

@app.route('/form')
def form():
    # Проверяем наличие и валидность токена авторизации
    user_account = UserAccount(session.get('email'))
    if user_account.is_token_valid() or user_account.refresh_token():
        # Если пользователь авторизован, перенаправляем на форму проверяем токен
        patients = ["Олег", "Оля", "Милана"]
        return render_template('form.html', email=user_account.email, patients=patients)
    else:
        # Если пользователь не авторизован, перенаправляем на страницу логина
        print("Нужно пройти авторизацию")
        return redirect(url_for('login'))


@app.route('/upload', methods=['POST'])
def upload():
    email = session.get('email')  # Используем email из сессии
    user_account = UserAccount(email)
    # Извлекаем имя пользователя из email (часть до символа '@')
    username = email.split('@')[0]

    if not user_account.is_token_valid():
        return flask.redirect('authorize')

    # Получаем данные из формы
    form_data = {
        "account": user_account.email,
        "category": "medicine",
        "subject": request.form.get("subject"),
        "uploadingDate": time.strftime('%d.%m.%Y'),  # Текущая дата
        "eventDate": datetime.strptime(request.form.get("eventDate"), '%Y-%m-%d').strftime('%d.%m.%Y')
                  if request.form.get("eventDate") else None,  # Преобразуем и присваиваем дату
        "patient": request.form.get("patient"),
        "city": "Санкт-Петербург",  # По умолчанию
        "clinic": request.form.get("clinic"),
        "doctorSpec": request.form.get("doctorSpec"),
        "doctorName": request.form.get("doctorName"),
        "diagnosis": request.form.get("diagnosis"),
        "comment": request.form.get("comment"),
    }

    # Проверяем наличие файлов
    if 'file' not in request.files:
        flash("No files selected for uploading.", "error")
        return redirect(url_for('form'))

    files = request.files.getlist('file')
    attached_files = []

    for file in files:
        if file:
            # Формируем путь подпапки для пользователя
            user_folder = os.path.join(app.config['UPLOAD_FOLDER'], username)
            # Создаем папку пользователя, если её не существует
            if not os.path.exists(user_folder):
                os.makedirs(user_folder)
            # Сохраняем каждый файл во временную папку
            temp_filepath = os.path.join(user_folder, file.filename)
            file.save(temp_filepath)

            # Записываем в структуру имя файла
            attached_files.append({'fileName': file.filename})


    form_data["attachedFiles"] = attached_files
    print(f"Collected form data: {form_data}")  # Для отладки

    try:

        # Публикация в RabbitMQ
        publisher = Publisher()
        publisher.send_message(json.dumps(form_data))
        publisher.close()

        flash('Files sent successfully!', 'success')

    except Exception as e:
        flash('Something went wrong, please try later!', 'failure')

    return redirect(url_for('form'))


@app.route("/logout")
def logout():
    user_account = UserAccount(session.get('email'))
    if user_account.revoke_token() or user_account.refresh_token():
        # Чистим сессию и редиректим
        session.clear()
        flash('Credentials successfully revoked.')
        return render_template('redirect_with_delay.html')
    else:
        return 'Failed to revoke credentials.'


if __name__ == '__main__':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
    app.run('0.0.0.0', 8080, debug=True)