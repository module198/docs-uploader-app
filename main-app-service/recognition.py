import base64
from openai import OpenAI
import json
import re
from utils import *

# Function to encode the image
def encode_image(file_storage):
    return base64.b64encode(file_storage.read()).decode("utf-8")

def call_openai_recognition(file):
    #Допилить через ENV
    client = OpenAI(
      api_key=api_key
    )
    try:
        # Getting the Base64 string
        base64_image = encode_image(file)
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        { "type": "text", "text": "На изображении находится документ из медицинского центра. Пожалуйста, извлеки и верни следующую информацию в JSON-формате: 1.patient: ФИО пациента, 2. clinic: Название медцентра, 3. eventDate: Дата приёма, 4. doctorName: ФИО врача/доктора, 5. doctorSpec: Специализация врача, 6. diagnosis: Диагноз, 7. city: Город местонахождения данного центра, 8. subject: Краткое название документа(1-2 слова, например: Осмотр; Заключение; Справка). Если какая-либо информация отсутствует — укажи null." },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
        )

        response_text = completion.choices[0].message.content

        # Находим "чистый" JSON в тексте
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            json_str = match.group(0)
            response_dict = json.loads(json_str)
            logger.info('Recognized data: %s', response_dict)
        else:
            logger.info("Не удалось найти JSON в ответе.")

        return response_dict
    except Exception as e:
        logger.error(e)
        return {}
