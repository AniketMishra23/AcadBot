import requests
import os
import dotenv

dotenv.load_dotenv()
api_key = os.getenv("CHATPDF_API")


def doc_qna(bot_token, file_id, filename, api_key):
    # Construct the URL for getting file information
    get_file_path = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"

    # Make a request to get file information
    response = requests.get(get_file_path)
    data = response.json()
    file_path = data['result']['file_path']
    # print(file_path)

    file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"

    # Download the file from Telegram
    file_response = requests.get(file_url)
    with open(f'{filename}', "wb") as file:
        file.write(file_response.content)
    print(f'{filename}', "downloaded successfully from Telegram.")

    path = f'{filename}'
    # Call the ChatPDF API
    files = [
        ('file', ('file', open(f'{path}', 'rb'),
         'application/octet-stream'))
    ]
    headers = {
        'x-api-key': api_key
    }

    response = requests.post(
        'https://api.chatpdf.com/v1/sources/add-file', headers=headers, files=files)

    return response.json()['sourceId']


def chatpdf_chat(api_key, questions, sourceID):
    headers = {
        'x-api-key': api_key,
        "Content-Type": "application/json",
    }

    data = {
        'sourceId': sourceID,
        'messages': [
            {
                'role': "user",
                'content': questions,
            }
        ]
    }

    response = requests.post(
        'https://api.chatpdf.com/v1/chats/message', headers=headers, json=data)

    return response.json()['content']
