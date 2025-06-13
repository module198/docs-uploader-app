from utils import *

def call_openai_recognition(file):
    """
    Sends a file object to the FastAPI document recognition endpoint.

    Parameters:
    - file (FileStorage): File-like object from Flask's request.files['file']
    - api_key (str): API key for authorization header.
    - url (str): Endpoint to send the file to.

    Returns:
    - dict: JSON response from the FastAPI server.
    """
    headers = {
        "X-API-Key": pi_api_key,
    }

    files = {
        "file": (file.filename, file.stream, file.mimetype or "application/octet-stream")
    }

    try:
        response = requests.post(url=pi_api_url, headers=headers, files=files)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        logger.error(e)
    except Exception as e:
        logger.error(e)

    return {}
