import requests
import os
import dotenv
import logging

dotenv.load_dotenv()

logger = logging.getLogger(__name__)


def doc_qna(bot_token, file_id, filename, api_key):
    """
    Downloads the file from Telegram, uploads it to ChatPDF, and returns
    (source_id, local_file_path). The caller is responsible for deleting
    the local file after use.
    """
    # Get the file path on Telegram's servers
    get_file_path = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
    response = requests.get(get_file_path, timeout=15)
    response.raise_for_status()

    data = response.json()
    file_path = data['result']['file_path']
    file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"

    # Download the file locally
    file_response = requests.get(file_url, timeout=30)
    file_response.raise_for_status()

    local_path = filename
    with open(local_path, "wb") as f:
        f.write(file_response.content)
    logger.info(f"Downloaded file from Telegram: {local_path}")

    # Upload to ChatPDF
    with open(local_path, 'rb') as f:
        files = [('file', ('file', f, 'application/octet-stream'))]
        headers = {'x-api-key': api_key}
        upload_response = requests.post(
            'https://api.chatpdf.com/v1/sources/add-file',
            headers=headers,
            files=files,
            timeout=30
        )

    upload_response.raise_for_status()
    source_id = upload_response.json().get('sourceId')

    if not source_id:
        raise ValueError("ChatPDF did not return a sourceId.")

    logger.info(f"ChatPDF sourceId obtained: {source_id}")
    return source_id, local_path


def chatpdf_chat(api_key, question, source_id):
    """Send a question about a previously uploaded PDF and return the answer."""
    headers = {
        'x-api-key': api_key,
        "Content-Type": "application/json",
    }
    data = {
        'sourceId': source_id,
        'messages': [
            {'role': "user", 'content': question}
        ]
    }

    response = requests.post(
        'https://api.chatpdf.com/v1/chats/message',
        headers=headers,
        json=data,
        timeout=30
    )
    response.raise_for_status()

    content = response.json().get('content')
    if not content:
        raise ValueError("ChatPDF returned an empty response.")

    return content
