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
    "HackingToolsEquipment": "809d9ef5687b9646576866c6e9a8328463f1",
    "HackingServices": "ec22a14a358fa3485d3aadf360f6e7a1f4ad",
    "Hosting": "56c4c1950932f04c3408b860ddecd11bd6d7",
    "SoftwareMalware": "b17198b32cad9244b42bf2a28761a1cc9dca",
}

# Cookies required by Nexus
cookies = ""
headers = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": cookies,
}

def request(urls):
    for category, url in urls.items():
        print(f"Fetching: {category}")
        page = 1
        
        while True:
            paged_url= f"{base_url}/products/{url}/?page={page}"
            try:
                response = requests.get(paged_url, headers=headers, proxies=proxies)
                
                if response.status_code != 200:
                    print(f"End of {category} or failed with {response.status_code}")
                    break
                soup = BeautifulSoup(response.text, 'html.parser')
                product = soup.find_all("div", class_="flex-1 border-2 border-slate-900 shadow rounded-xl pb-2 relative")
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
    product = soup.find_all("div", class_="flex-1 border-2 border-slate-900 shadow rounded-xl pb-2 relative")

    file_exists = os.path.exists("nexus_products.csv")
    with open("nexus_products.csv", "a", newline='', encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(["Category","ProductId","Title", "PaymentType", "Vendor", "Price", "Currency", "Date"])  # header

        for card in product:
            productId = card.find("a", href=True)["href"].split("/")[-1]
            title = '"' + card.find("a", class_="font-semibold text-base md:text-md text-primary hover:text-base-500 duration-[750ms] line-clamp-3").get_text(strip=True) + '"'
            vendor = card.find("div", class_="font-heading text-xs font-bold truncate").get_text(strip=True)
            paymentType = card.find("span", class_="font-semibold").get_text(strip=True)
            price = card.find("span", class_="font-bold").get_text(strip=True)
            currency = card.find("span", class_="text-lg").get_text(strip=True).split()[0][-3:]

            writer.writerow([category, productId, title, paymentType, vendor, price, currency, date.today()])
            
            
request(urls)
