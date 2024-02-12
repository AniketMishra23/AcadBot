from urllib.parse import urlparse

url = "https://randomclassess.netlify.app/resource"
parsed_url = urlparse(url)
base_url = parsed_url.scheme + "://" + parsed_url.netloc

print(base_url)