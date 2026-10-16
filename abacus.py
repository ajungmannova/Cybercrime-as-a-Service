from bs4 import BeautifulSoup
from datetime import date
import requests
import csv
import time
import os
import traceback

proxies = {
    "http": "socks5h://127.0.0.1:9062",
    "https": "socks5h://127.0.0.1:9062"
}

base_url = ""

# Category endpoints
urls = {
    "Hosting": "/search?fcats[]=79c2a100af215da6d3987ea6&s_category=&cats=2&s_crypto=&s_terms=&s_sellername=&s_lphysical=2&s_minprice=0.00&s_maxprice=9999.99&s_countryid=-1&s_tocountryid=-1&s_discardww=0&s_fulfill=2&s_multisig=2&s_bulk=2&s_stock=2&s_payment=0&s_order=0&pg=",
    "BotnetMalware": "/search?adv=on&s_terms=&s_sellername=&s_order=0&s_tocountryid=-1&s_countryid=-1&s_category=475756f633d0cc71f0c868bd&fcats[]=1a147b7d876b0943ca470427&fcats[]=475756f633d0cc71f0c868bd&s_lphysical=2&s_minprice=0.00&s_maxprice=99999.99&s_crypto=0&s_fulfill=2&s_multisig=2&s_bulk=2&s_stock=2&s_payment=0",
    "Exploits": "/search?fcats[]=475756f633d0cc71f0c868bd&s_category=&cats=2&s_crypto=&s_terms=&s_sellername=&s_lphysical=2&s_minprice=0.00&s_maxprice=9999.99&s_countryid=-1&s_tocountryid=-1&s_discardww=0&s_fulfill=2&s_multisig=2&s_bulk=2&s_stock=2&s_payment=0&s_order=0&pg=5",
    "ExploitKits": "/search?adv=on&s_terms=&s_sellername=&s_order=0&s_tocountryid=-1&s_countryid=-1&s_category=4e5630455a6f16bf43092060&fcats[]=1a147b7d876b0943ca470427&fcats[]=449a1f423b9c4fc39ffa3956&s_lphysical=2&s_minprice=0.00&s_maxprice=99999.99&s_crypto=0&s_fulfill=2&s_multisig=2&s_bulk=2&s_stock=2&s_payment=0",
    "SecuritySoftware": "/search?adv=on&s_terms=&s_sellername=&s_order=0&s_tocountryid=-1&s_countryid=-1&s_category=c7da5f6d7fed7ebd27e4ea75&fcats%255B%255D=1a147b7d876b0943ca470427&fcats%255B%255D=c7da5f6d7fed7ebd27e4ea75&s_lphysical=2&s_minprice=0.00&s_maxprice=99999.99&s_crypto=0&s_fulfill=2&s_multisig=2&s_bulk=2&s_stock=2&s_payment=0",
}

# Cookies required by Nexus
cookies = ""
headers = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": cookies,
}

def request(urls):
    for category, url_endpoint in urls.items():
        print(f"Fetching: {category} pages")
        page = 1
        
        while True:
            url= f"{base_url}{url_endpoint}"     
            try:
                response = requests.get(url, headers=headers, proxies=proxies, verify=False)
                if response.status_code != 200:
                    print(f"End of {category} or failed with {response.status_code}")
                    break
                soup = BeautifulSoup(response.text, 'html.parser')
                product = soup.find_all("div", class_="src-listing p-1 pb-0 flex flex-col justify-between w-full rounded-md border-solid border-[1px] !border-border !bg-white hover:!bg-hover hover:!border-abacus2 !mt-0")
                if not product:
                    print(f"No products on page {category}, page: {page}")
                    break
                    
                scrape(soup, category)
                print(f"Processed: {category} page {page}")
                next_link = soup.find("a", class_="h-full px-3 rounded-md text-abacus bg-white border border-border hover:bg-abacus2 hover:text-white")
                if next_link:
                    next_href = next_link.get("href", "")
                    if next_href.strip() == "#" or not next_href.strip():
                        print("Reached last page.")
                        break
                    else:
                        url = f"{base_url}{next_href}"                        
                
                time.sleep(2)
                page += 1

            except requests.RequestException as req_err:
                print(f"Network error: {req_err}")

            except Exception as e:
                print(f"Error fetching {category}: {e}")
                traceback.print_exc()



def scrape(soup, category):
    product = soup.find_all("div", class_="src-listing p-1 pb-0 flex flex-col justify-between w-full rounded-md border-solid border-[1px] !border-border !bg-white hover:!bg-hover hover:!border-abacus2 !mt-0")

    seen_today = set()

    file_exists = os.path.exists("abacus_products.csv")
    with open("abacus_products.csv", "a", newline='', encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(["Category", "ProductId", "Title", "PaymentType", "Vendor", "Price", "Currency", "Date"])


        for card in product:
            productId = card.find("a", class_="text-xs font-bold text-abacus", href=True)["href"].split("/")[-1]
            title = '"' + card.find("a", class_="text-xs font-bold text-abacus").get_text(strip=True) + '"'
            vendor = card.find("div", class_="flex flex-wrap items-center gap-1").get_text(strip=True)
            paymentType = card.find("span", class_="flex flex-wrap items-center gap-1").get_text(strip=True)
            raw_price = card.find("div", class_="text-sm text-abacus2 font-bold text-center").get_text(strip=True)
            currency, price = raw_price.split()
            
            if (category, productId, price, date.today()) in seen_today:
                continue

            seen_today.add((category, productId, price, date.today()))

            writer.writerow([category, productId, title, paymentType, vendor, price, currency, date.today()])
            

request(urls)

