import flask
from flask import Flask, redirect, url_for, session, request, render_template, flash
import google_auth_oauthlib.flow
from utils import *
import time
from datetime import datetime
from rabbit_publish import Publisher
import json
app = Flask(__name__)
app.secret_key = os.urandom(24)

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
        logger.info("Токен не валиден")
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
    if environment == 'local':
        flow.redirect_uri = flask.url_for('oauth2callback', _external=True)
    elif environment == 'production':
        flow.redirect_uri = env_redirect_uri
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
    if environment == 'local':
        flow.redirect_uri = flask.url_for('oauth2callback', _external=True)
    elif environment == 'production':
        flow.redirect_uri = env_redirect_uri

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

    return flask.redirect('/form')

@app.route('/form')
def form():
    # Проверяем наличие и валидность токена авторизации
    user_account = UserAccount(session.get('email'))
    if user_account.is_token_valid() or user_account.refresh_token():
        # Если пользователь авторизован, перенаправляем на форму проверяем токен
        dictionaries = user_account.load_dictionaries()
        patients = dictionaries.get('patients', [])
        subjects = dictionaries.get('subjects', [])
        cities = dictionaries.get('cities', [])

        # Определяем, с какого устройства зашёл пользователь
        user_agent = request.user_agent.string.lower()
        if any(keyword in user_agent for keyword in ("mobile", "android", "iphone")):
            return render_template('form_mobile.html',
                                   email=user_account.email,
                                   patients=patients,
                                   subjects=subjects,
                                   cities=cities)

        else:
            return render_template('form_pc.html',
                                   email=user_account.email,
                                   patients=patients,
                                   subjects=subjects,
                                   cities=cities)
    else:
        # Если пользователь не авторизован, перенаправляем на страницу логина
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
        "city": request.form.get("city"),
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
            os.makedirs(user_folder, exist_ok=True)
            # if not os.path.exists(user_folder):
            #     os.makedirs(user_folder)
            # Сохраняем каждый файл во временную папку
            temp_filepath = os.path.join(user_folder, file.filename)
            file.save(temp_filepath)

            # Записываем в структуру имя файла
            attached_files.append({'fileName': file.filename})


    form_data["attachedFiles"] = attached_files

    try:

        # Публикация в RabbitMQ
        publisher = Publisher()
        publisher.send_message(json.dumps(form_data,ensure_ascii=False))
        publisher.close()
        # Логирование успешной публикации
        logger.info('Message sent successfully to RabbitMQ with data: %s', form_data)

        flash('Files sent successfully!', 'success')

    except Exception as e:
        # Логирование ошибки
        # logger.exception('Failed to send message to RabbitMQ: %s', str(e))
        logger.exception('Failed to send message to RabbitMQ: %s, user: %s, data: %s', str(e), user_account.email,
                         form_data)

        flash('Something went wrong, please try later. Error: ' + str(e), 'failure')

    return redirect(url_for('form'))


@app.route("/logout")
def logout():
    user_account = UserAccount(session.get('email'))
    # Чистим сессию и редиректим
    session.clear()
    logger.info('Successfully logged out.: %s', user_account)
    flash('You successfully logged out.')
    return render_template('redirect_with_delay.html')


@app.route("/revoke")
def revoke():
    user_account = UserAccount(session.get('email'))
    if user_account.revoke_token() or user_account.refresh_token():
        # Чистим сессию и редиректим
        session.clear()
        logger.info('Credentials successfully revoked.: %s', user_account)
        flash('Credentials successfully revoked.')
        return render_template('redirect_with_delay.html')
    else:
        # Логирование ошибки
        logger.info('Failed to revoke credentials.: %s', user_account)
        return 'Failed to revoke credentials.'


@app.route('/dictionaries')
def dictionaries():
    # Проверяем наличие и валидность токена авторизации
    user_account = UserAccount(session.get('email'))
    if user_account.is_token_valid() or user_account.refresh_token():
        # Если пользователь авторизован, перенаправляем на форму проверяем токен
        dictionaries = user_account.load_dictionaries()
        patients = dictionaries.get('patients', [])
        subjects = dictionaries.get('subjects', [])
        cities = dictionaries.get('cities', [])

        # Определяем, с какого устройства зашёл пользователь
        user_agent = request.user_agent.string.lower()
        if any(keyword in user_agent for keyword in ("mobile", "android", "iphone")):
            return render_template('dictionaries_mobile.html',
                                   email=user_account.email,
                                   patients=patients,
                                   subjects=subjects,
                                   cities=cities)

        else:
            return render_template('dictionaries_pc.html',
                                   email=user_account.email,
                                   patients=patients,
                                   subjects=subjects,
                                   cities=cities)
    else:
        # Если пользователь не авторизован, перенаправляем на страницу логина
        return redirect(url_for('login'))


@app.route('/save_dictionaries_to_file', methods=['POST'])
def save_dictionaries_to_file():
    """Обрабатывает данные формы и сохраняет их в справочники."""
    email = session.get('email')  # Используем email из сессии
    user_account = UserAccount(email)

    if not user_account.is_token_valid():
        return flask.redirect('authorize')

    dictionaries = user_account.load_dictionaries()

    # Получаем существующие данные
    patients = set(dictionaries.get("patients", []))
    subjects = set(dictionaries.get("subjects", []))
    cities = set(dictionaries.get("cities", []))

    # Получаем выбранные и новые значения
    selected_patient = request.form.get("patient")
    new_patients = request.form.getlist("new_patient[]")

    selected_subject = request.form.get("subject")
    new_subjects = request.form.getlist("new_subject[]")

    selected_city = request.form.get("city")
    new_cities = request.form.getlist("new_city[]")

    logger.info(f"Значения с формы ведения справочников получены: {new_patients}, {new_subjects}, {new_cities}")
    # Добавляем новые значения, если они введены
    patients.update(filter(None, new_patients))
    subjects.update(filter(None, new_subjects))
    cities.update(filter(None, new_cities))

    if selected_patient:
        patients.add(selected_patient)
    if selected_subject:
        subjects.add(selected_subject)
    if selected_city:
        cities.add(selected_city)

    # Обновляем справочник и сохраняем
    updated_data = {
        "patients": list(patients),
        "subjects": list(subjects),
        "cities": list(cities)
    }
    logger.info('Updated data: %s', updated_data)
    user_account.save_dictionaries(updated_data)

    return redirect("/")  # Перенаправляем пользователя обратно на форму


if __name__ == '__main__':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
    app.run('0.0.0.0', 8080, debug=False)