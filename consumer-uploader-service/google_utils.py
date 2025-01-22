from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload
from utils import *  # Импортируем функции из utils.py
from googleapiclient.errors import HttpError
import json
import io


def files_uploading(form_data):
# Загружаем файл на Google Drive
    account = form_data.get('account')
    user_account = UserAccount(account)
    username = account.split('@')[0]
    try:
        drive_service = build('drive', 'v3', credentials=user_account.credentials)
        # Получение ID папок для загрузки на google drive
        drive_structure = initialize_folder_structure(drive_service,
                                                     form_data.get("category"),
                                                     form_data.get("patient"),
                                                     form_data.get("eventDate")[-4:])
        for file in form_data.get('attachedFiles'):
            # Загрузка файла
            file_metadata = {
                'name': f'{form_data.get("eventDate")}_'
                        f'{form_data.get("clinic")}_'
                        f'{form_data.get("doctorSpec")}_'
                        f'{file.get("fileName")}',
                'parents': [drive_structure.get("yearFolderId")]  # ID папки
            }
            temp_filepath = f'{UPLOAD_FOLDER}/{username}/{file.get("fileName")}'
            logger.info(f'Uploading of {file.get("fileName")} started')
            media = MediaFileUpload(temp_filepath, mimetype='application/octet-stream')
            drive_response = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            #Получение fileID на гугл диске
            file_id = drive_response['id']
            logger.info(f'Upload of {file.get("fileName")} completed')

            # Делаем файл доступным для всех с ссылкой
            permission = {
                'type': 'anyone',
                'role': 'reader'  # Разрешение только на чтение
            }
            drive_service.permissions().create(
                fileId=file_id,
                body=permission
            ).execute()

            # Получаем ссылку на файл
            file_url = f'https://drive.google.com/file/d/{file_id}/view?usp=sharing'

            # Записываем в структуру ID и ссылку на файл
            file.update({'fileId': file_id, 'fileLink': file_url})

        # Делаю бэкап записи в JSON на Gdrive
        add_data_to_backup_json(drive_service, drive_structure.get('backup_json_id'), form_data)

        #Записываю в шитс
        update_or_create_sheet(drive_structure.get('sheetId'),
                               form_data,
                               user_account.credentials)

    except Exception as e:
        logger.exception(f'Error uploading file: {e}')


def initialize_folder_structure(drive_service, category, patient, year):
    """Инициализирует и возвращает структуру папок в Google Drive, включая создание необходимых папок и документа."""

    # 1. Найдем или создадим основную папку "DocsArchive" в корне
    main_folder_id = find_or_create_folder(drive_service, "DocsArchive")
    if not main_folder_id:
        raise ValueError("Не удалось найти или создать основную папку 'DocsArchive'.")

    # 2. Найдем или создадим папку по категории внутри "DocsArchive"
    category_folder_id = find_or_create_folder(drive_service, category, main_folder_id)
    if not category_folder_id:
        raise ValueError(f"Не удалось найти или создать папку категории '{category}' внутри 'DocsArchive'.")

    # 3. Найдем или создадим папку по пациенту внутри категории
    patient_folder_id = find_or_create_folder(drive_service, patient, category_folder_id)
    if not patient_folder_id:
        raise ValueError(f"Не удалось найти или создать папку пациента '{patient}' внутри категории '{category}'.")

    # 4. Найдем или создадим папку по году внутри пациента
    year_folder_id = find_or_create_folder(drive_service, year, patient_folder_id)
    if not year_folder_id:
        raise ValueError(f"Не удалось найти или создать папку года '{year}' внутри пациента '{patient}'.")

    # 5. Найдем или создадим Google Sheet документ 'documents list' внутри папки по году
    sheet_id = find_or_create_sheet(drive_service, main_folder_id)
    if not sheet_id:
        raise ValueError(
            f"Не удалось найти или создать документ Google Sheet 'documents list' в папке по году '{year}'.")

    # 6. Найдём JSON для хранения данных в рамках бэкапа
    backup_json_id = find_or_create_json(drive_service, main_folder_id)
    if not backup_json_id:
        raise ValueError("Не удалось найти или создать файл JSON для хранения данных в рамках бэкапа.")

    # Возвращаем все ID в виде словаря
    return {
        "mainFolderId": main_folder_id,
        "categoryFolderId": category_folder_id,
        "patientFolderId": patient_folder_id,
        "yearFolderId": year_folder_id,
        "sheetId": sheet_id,
        "backup_json_id": backup_json_id
    }


def find_or_create_sheet(drive_service, folder_id, sheet_name="documents list") -> str:
    """Ищет Google Sheets документ по имени в указанной папке, если не находит — создает его."""
    query = f"mimeType='application/vnd.google-apps.spreadsheet' and name='{sheet_name}' and '{folder_id}' in parents"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    if items:
        # Документ найден
        return items[0]['id']
    else:
        # Документ не найден, создаем
        file_metadata = {
            'name': sheet_name,
            'mimeType': 'application/vnd.google-apps.spreadsheet',
            'parents': [folder_id]
        }
        try:
            file = drive_service.files().create(body=file_metadata, fields='id').execute()
            return file['id']
        except HttpError as error:
            logger.exception(f"Error creating spreadsheet '{sheet_name}': {error}")
            return None


def find_or_create_json(drive_service, folder_id, json_name="data.json") -> str:
    """Ищет файл с расширением JSON по имени в указанной папке, если не находит — создает его."""
    query = f"mimeType='application/json' and name='{json_name}' and '{folder_id}' in parents"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    if items:
        # Файл найден
        return items[0]['id']
    else:
        # Файл не найден, создаем новый
        file_metadata = {
            'name': json_name,
            'mimeType': 'application/json',
            'parents': [folder_id]
        }
        try:
            file = drive_service.files().create(body=file_metadata, fields='id').execute()
            return file['id']
        except HttpError as error:
            logger.exception(f"Error creating JSON file '{json_name}': {error}")
            return None


def find_or_create_folder(drive_service, folder_name, parent_folder_id='root'):
    """Ищет папку по имени в указанной папке (или в корне), если не находит — создает её."""
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and '{parent_folder_id}' in parents"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    if items:
        # Папка найдена
        return items[0]['id']
    else:
        # Папка не найдена, создаем
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_folder_id]
        }
        try:
            folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
            return folder['id']
        except HttpError as error:
            logger.exception(f"Error creating folder '{folder_name}': {error}")
            return None


def update_or_create_sheet(sheet_id, data_sheet, credentials):
    """
    Обновляет или создает лист в Google Sheets, учитывая несколько файлов в 'attachedFiles'.
    Каждому файлу из 'attachedFiles' будет выделена отдельная строка с общей информацией и ссылками на файлы.
    Также добавляется уникальный 'record_id', который увеличивается только для новой записи, если уже есть существующие.

    :param sheet_id: ID Google Sheets документа.
    :param category: Название листа, которое нужно проверить или создать.
    :param data_sheet: Данные в виде JSON, которые нужно добавить в таблицу.
    :param credentials: Учетные данные для Google API.
    :return: None
    """
    category = data_sheet.get('category')
    try:
        # Создаем сервис для работы с Google Sheets
        sheets_service = build('sheets', 'v4', credentials=credentials)

        # Получаем информацию о всех листах в таблице
        spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        sheet_titles = [sheet['properties']['title'] for sheet in spreadsheet['sheets']]

        # Проверяем, существует ли лист с названием категории
        if category not in sheet_titles:
            # Если лист не найден, создаем его
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={ "requests": [{"addSheet": {"properties": {"title": category}}}] }
            ).execute()
            logger.info(f"Лист '{category}' был создан.")

        # Получаем данные из существующего или только что созданного листа
        range_ = f'{category}!A1:Z100000'
        result = sheets_service.spreadsheets().values().get(spreadsheetId=sheet_id, range=range_).execute()
        existing_values = result.get('values', [])

        # Если лист пустой, записываем заголовки (ключи JSON) и значения (данные из JSON)
        headers = ['record_id'] + [key for key in data_sheet.keys() if key != 'attachedFiles']  # Исключаем 'attachedFiles'
        if 'attachedFiles' in data_sheet:
            # Дополняем заголовки дополнительными полями для файлов
            file_headers = ['fileName', 'fileId', 'fileLink']
            headers.extend(file_headers)

        # Если лист пустой, записываем заголовки в первую строку
        if not existing_values:
            sheets_service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f'{category}!A1',
                valueInputOption="RAW",
                body={"values": [headers]}
            ).execute()
            logger.info(f"Заголовки были записаны в лист '{category}'.")
            last_record_id = 0  # Начинаем с 0, потому что будем смотреть на последний записанный record_id
        else:
            # Если записи уже есть, находим последний record_id
            record_ids = [int(row[0]) for row in existing_values if row[0].isdigit()]
            last_record_id = max(record_ids) if record_ids else 0  # Находим максимальный record_id

        # Теперь работаем с файлами и основной информацией
        attached_files = data_sheet.get('attachedFiles', [])
        base_data = {key: value for key, value in data_sheet.items() if key != 'attachedFiles'}

        # Для всех файлов в этой загрузке будем использовать одинаковый record_id
        record_id_for_current_batch = str(last_record_id + 1).zfill(5)

        # Для каждого файла добавляем строку с одинаковым record_id
        for file_data in attached_files:
            # Формируем строку с общими данными
            row_to_add = [record_id_for_current_batch] + list(base_data.values())  # Добавляем одинаковый record_id для всех файлов

            # Добавляем информацию о файле
            file_info = [
                file_data.get('fileName', ''),
                file_data.get('fileId', ''),
                file_data.get('fileLink', '')
            ]
            row_to_add.extend(file_info)

            # Добавляем новую строку с данными
            sheets_service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=f'{category}!A1',
                valueInputOption="RAW",
                body={"values": [row_to_add]},
                insertDataOption="INSERT_ROWS"  # Вставить новую строку
            ).execute()

        logger.info(f"Данные были добавлены в лист '{category}'.")

    except HttpError as err:
        logger.exception(f"Ошибка работы с Google Sheets: {err}")


def add_data_to_backup_json(drive_service, file_id, data):
    """
    Добавляет данные в файл JSON на Google Drive. Если файл пустой, записываются данные.
    Если файл не пустой, данные добавляются в конец.

    :param drive_service: Сервис для работы с Google Drive API.
    :param file_id: ID файла на Google Drive.
    :param data: Данные для добавления в файл JSON (в виде словаря).
    :return: None
    """
    try:
        # Попытка скачать содержимое файла JSON с Google Drive
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False

        while not done:
            status, done = downloader.next_chunk()

        # Загружаем содержимое файла
        fh.seek(0)
        file_content = fh.read().decode("utf-8")

        # Если файл не пустой, добавляем данные в конец
        if file_content:
            json_data = json.loads(file_content)
            if not isinstance(json_data, list):
                json_data = []  # Приводим структуру данных к списку, если она не является списком
            json_data.append(data)
        else:
            # Если файл пустой, создаем новый список с данными
            json_data = [data]

    except HttpError as e:
        # Если файл не существует или не может быть прочитан
        print(f"Ошибка при чтении файла: {e}")
        # Создаем новый список с данными в случае ошибки
        json_data = [data]

    except Exception as e:
        # Ловим другие ошибки
        print(f"Ошибка при чтении файла: {e}")
        # В случае ошибок создаем новый файл с данными
        json_data = [data]

    # Сохраняем обновленный файл обратно на Google Drive
    file_metadata = {'name': 'backup_data.json'}  # Имя файла можно оставить или изменить
    media = MediaIoBaseUpload(io.BytesIO(json.dumps(json_data).encode('utf-8')), mimetype='application/json')

    try:
        # Обновляем файл на Google Drive
        drive_service.files().update(fileId=file_id, body=file_metadata, media_body=media).execute()
        print(f"Данные успешно добавлены в файл с ID {file_id}")
    except HttpError as e:
        print(f"Ошибка при обновлении файла на Google Drive: {e}")
    except Exception as e:
        print(f"Ошибка при обновлении файла: {e}")

