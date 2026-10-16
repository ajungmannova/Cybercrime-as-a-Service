from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from wordcloud import WordCloud
# --------------------------- HARDCODED STOPWORDS -----------------------

STOPWORDS = {
    "Super","Premium","Best","Pack","[AUTODISPATCH]","autodispatch",
    "top","very","fast","from","to","all","about","professional","warrenty","pro",
    "get","your","own","way","and","now","released","build","any","most","you","today",
    "for","instant","delivery","latest","version","free","edition","the","download",
    "new","versions","with","easy","includes","plus","without","become","bundle",
    "monthly","ultimate","000","lifetime","activated","full","more","what","where",
    "will","mega","non","weekly","also","including","one","per","self","special",
    "them","yourself","complete","extras","anyone","day","never","title","thousands",
    "unlimited","updated","can","are","who","collection","make","master","success",
    "only","power","x64","via","extra","mastery","step","megapack","diabolic"
}

def _tokenize(text):
    tokens = re.findall(r'\b[a-z]{3,}\b', str(text).lower())
    return [t for t in tokens if t not in STOPWORDS]

def generate_frequency_list(df, category, output_dir):
    """Saves a CSV of sorted keywords for a category (Section 1.1.4)"""
    unique_products = df.drop_duplicates(subset=['ProductId']).copy()
    cat_df = unique_products[unique_products['ActualCategory'] == category]
    all_tokens = []
    for title in cat_df['Title']:
        all_tokens.extend(_tokenize(title))
    
    freq = Counter(all_tokens).most_common(100)
    out_df = pd.DataFrame(freq, columns=['word', 'count'])
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    safe_name = category.replace("/", "_")
    out_df.to_csv(f"{output_dir}/{safe_name}_FreqWords.csv", index=False)

def create_category_wordcloud(df, category, output_dir):
    """Generates a wordcloud for a category (Section 1.1.4)"""
    unique_products = df.drop_duplicates(subset=['ProductId']).copy()
    cat_df = unique_products[unique_products['ActualCategory'] == category]
    text = " ".join(cat_df['Title'].apply(lambda x: " ".join(_tokenize(x))))
    
    wc = WordCloud(width=800, height=400, background_color='white').generate(text)
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    safe_name = category.replace("/", "_")
    plt.figure(figsize=(10, 5))
    plt.imshow(wc, interpolation='bilinear')
    plt.axis("off")
    plt.savefig(f"{output_dir}/{safe_name}_wordcloud.png")
    plt.close()
