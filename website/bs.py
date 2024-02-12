import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse


def web_scrape(url, base_url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    links = soup.find_all("a")

    # Initialize a list to store PDF links
    name = []
    for link in links:
        href = link.get("href")
        if href and href.endswith(".pdf"):
            name.append(href)
            # print(href)
        # print(name)

    pdf_links = []
    for i in range(len(name)):
        a = f"{base_url}" + "/" + name[i]
        pdf_links.append(a)
        # print(pdf_links)
    return pdf_links


url = input("Enter the url: ")  # Replace with your actual URL
parsed_url = urlparse(url)
base_url = parsed_url.scheme + "://" + parsed_url.netloc
result = web_scrape(url, base_url)
# print(result)

try:
    with open('website/pdflinks.txt', 'w') as f:
        for link in result:
            f.write(link + '\n')
except Exception as e:
    print(f"An error occurred while saving the output: {str(e)}")