from bs4 import BeautifulSoup
from datetime import date
import requests
import csv
import time
import os

proxies = {
    "http": "socks5h://127.0.0.1:9050",
    "https": "socks5h://127.0.0.1:9050"
}  

base_url = ""
# Category endpoints
urls = {
    "Malware & Botnet": "&cat=Cracked+softwares%2C+Botnets+%26+Malware&sub=Malware+%26+Botnets&sortby=default",
    "Exploits": "?cat=Security+%26+Hacking&sub=Exploits&sortby=default",
    "Hacking Software": "&cat=Security+%26+Hacking&sub=Hacking+Software&sortby=default",
    "Exploit Kits": "&cat=Security+%26+Hacking&sub=Hacking+Software&sortby=default",
    "Services": "&cat=Security+%26+Hacking&sub=Services&sortby=default",
}

# Cookies required by Nexus
cookies = ""
headers = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": cookies,
}

def request(urls):
    for category, url in urls.items():
        print(f"Fetching: {category} pages")
        page = 1
        
        while True:
            paged_url= f"{base_url}/?page={page}{url}"
            
            try:
                response = requests.get(paged_url, headers=headers, proxies=proxies, verify=False, timeout=30)
                print(response.text)
                if response.status_code != 200:
                    print(f"End of {category} or failed with {response.status_code}")
                    break
                soup = BeautifulSoup(response.text, 'html.parser')
                product = soup.find_all("div", class_="product-details pb-0 bg-b0b0b021")
                if not product:
                    print(f"No products on page {category}, page: {page}")
                    break
                    
                scrape(soup, category)

                print(f"Processed: {category} page {page}")
                
                time.sleep(2)
                page += 1

            except Exception as e:
                print(f"Error fetching {category}: {e}")


def scrape(soup, category):
    product = soup.find_all("div", class_="product-details pb-0 bg-b0b0b021")

    file_exists = os.path.exists("vortex_products.csv")
    with open("vortex_products.csv", "a", newline='', encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(["Category", "ProductId", "Title", "PaymentType", "Vendor", "Price", "Currency", "Date"])

        for card in product:
            productId = card.find("a", href=True)["href"].split("/")[-1]
            title = '"' + card.find("a", class_="mb-0 text-left text-warning text-363636-nothover-notfocus").get_text(strip=True) + '"'
            vendor = card.find("a", class_="d-inline-block w-auto mr-1 px-1 bg-primary text-white underline-0 font-weight-normal").get_text(strip=True)
            paymentType = card.find("span", class_="d-inline-block w-100 mx-0 px-1 bg-success text-white border rounded-1 font-weight-normal").get_text(strip=True)
            raw_price = card.find("div", class_="product-price d-inline-block w-100 mx-0 px-1 bg-success text-white border rounded-1").get_text(strip=True)
            if raw_price.startswith("$"):
                    currency = "USD"
                    price = raw_price[1:]
            elif raw_price.startswith("€"):
                currency = "EUR"
                price = raw_price[1:]
            else:
                currency = "UNKNOWN"
                price = raw_price

            writer.writerow([category, productId, title, paymentType, vendor, price, currency, date.today()])

request(urls)
