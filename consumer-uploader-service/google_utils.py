from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from utils import *  # Импортируем функцию из utils.py
from googleapiclient.errors import HttpError

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
            ######Допилить temp_filepath
            # temp_filepath = f'../shared/uploads/{username}/{file.get("fileName")}'
            temp_filepath = f'{UPLOAD_FOLDER}/{username}/{file.get("fileName")}'
            media = MediaFileUpload(temp_filepath, mimetype='application/octet-stream')
            drive_response = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            #Получение fileID на гугл диске
            file_id = drive_response['id']

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

            #Записываю в шитс
            # update_or_create_sheet(drive_structure.get('sheetId'), form_data.get("category"), form_data, credentials)

    except Exception as e:
        print(f'Error uploading file {e}')


def initialize_folder_structure(drive_service, category, patient, year):
    """Инициализирует и возвращает структуру папок в Google Drive, включая создание необходимых папок и документа."""

    # 1. Найдем или создадим основную папку "DocsArchive" в корне
    main_folder_id = find_or_create_folder(drive_service, "DocsArchive")

    if not main_folder_id:
        return {"mainFolderId": None, "patientFolderId": None, "yearFolderId": None, "sheetId": None}

    # 2. Найдем или создадим папку по категории внутри "DocsArchive"
    category_folder_id = find_or_create_folder(drive_service, category, main_folder_id)

    if not category_folder_id:
        return {"mainFolderId": main_folder_id, "patientFolderId": None, "yearFolderId": None, "sheetId": None}

    # 3. Найдем или создадим папку по пациенту внутри категории
    patient_folder_id = find_or_create_folder(drive_service, patient, category_folder_id)

    if not patient_folder_id:
        return {"mainFolderId": main_folder_id, "patientFolderId": category_folder_id, "yearFolderId": None,
                "sheetId": None}

    # 4. Найдем или создадим папку по году внутри пациента
    year_folder_id = find_or_create_folder(drive_service, year, patient_folder_id)

    if not year_folder_id:
        return {"mainFolderId": main_folder_id, "patientFolderId": patient_folder_id, "yearFolderId": None,
                "sheetId": None}

    # 5. Найдем или создадим Google Sheet документ 'documents list' внутри папки по году
    sheet_id = find_or_create_sheet(drive_service, main_folder_id)

    if not sheet_id:
        return {"mainFolderId": main_folder_id, "patientFolderId": patient_folder_id, "yearFolderId": year_folder_id,
                "sheetId": None}

    # Возвращаем JSON с ID всех папок и документа
    return {
        "mainFolderId": main_folder_id,
        "categoryFolderId": category_folder_id,
        "patientFolderId": patient_folder_id,
        "yearFolderId": year_folder_id,
        "sheetId": sheet_id
    }

def find_or_create_sheet(drive_service, folder_id, sheet_name="documents list"):
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
            print(f"Error creating spreadsheet '{sheet_name}': {error}")
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
            print(f"Error creating folder '{folder_name}': {error}")
            return None