# utils.py
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import kruskal
import scipy.stats as stats
import scikit_posthocs as sp
from scipy.stats import chi2_contingency

# ---------------------------- EXCHANGE RATES ------------------------
# Daily ECB euro reference rates (USD and GBP per 1 EUR), 19 May - 1 July 2025.
# Source: European Central Bank reference rates, retrieved via the Frankfurter API (api.frankfurter.dev).
# Each listing is converted at the last ECB fixing on or before its snapshot date
# (weekend snapshots use the preceding Friday). Replaces the earlier fixed rates (EUR 1.08, GBP 1.27).
ECB_RATES = {  # date: (EURUSD, EURGBP)
    "2025-05-19": (1.1262, 0.8419), "2025-05-20": (1.1241, 0.8418), "2025-05-21": (1.1321, 0.8446),
    "2025-05-22": (1.1309, 0.8427), "2025-05-23": (1.1301, 0.8382), "2025-05-26": (1.1381, 0.8392),
    "2025-05-27": (1.1356, 0.8381), "2025-05-28": (1.1317, 0.8398), "2025-05-29": (1.1281, 0.8377),
    "2025-05-30": (1.1339, 0.8412), "2025-06-02": (1.1419, 0.8434), "2025-06-03": (1.1386, 0.8436),
    "2025-06-04": (1.1384, 0.8421), "2025-06-05": (1.1423, 0.8419), "2025-06-06": (1.1411, 0.8426),
    "2025-06-09": (1.1410, 0.8424), "2025-06-10": (1.1429, 0.8464), "2025-06-11": (1.1433, 0.8476),
    "2025-06-12": (1.1594, 0.8538), "2025-06-13": (1.1512, 0.8505), "2025-06-16": (1.1574, 0.8523),
    "2025-06-17": (1.1568, 0.8525), "2025-06-18": (1.1508, 0.8552), "2025-06-19": (1.1478, 0.8541),
    "2025-06-20": (1.1515, 0.8537), "2025-06-23": (1.1472, 0.8567), "2025-06-24": (1.1607, 0.8527),
    "2025-06-25": (1.1598, 0.8526), "2025-06-26": (1.1695, 0.8535), "2025-06-27": (1.1704, 0.8529),
    "2025-06-30": (1.1720, 0.8555), "2025-07-01": (1.1810, 0.8588),
}

def usd_per_unit(currency, date):
    """USD value of one unit of `currency` on `date`, using the last ECB fixing on or before that date."""
    if currency == "USD":
        return 1.0
    day = max(d for d in ECB_RATES if d <= str(date))
    eurusd, eurgbp = ECB_RATES[day]
    return {"EUR": eurusd, "GBP": eurusd / eurgbp}[currency]

def clean_and_normalize(df, marketplace_name):
    """
    Standardizes a single marketplace dataset based on Section 1.1.2.
    """
    # 0. Drop empty lines and repair a double-encoding artefact in a few titles
    df = df.dropna(how='all').copy()
    df['Title'] = df['Title'].astype(str).str.replace('\u00ef\u00bf\u00bd', '\ufffd', regex=False)

    # 1. Normalize columns to lowercase and handle Price
    df['Price'] = df['Price'].replace(r'[^\d.]', '', regex=True).astype(float)

    # 2. Date Normalization (needed before currency conversion)
    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True).dt.date

    # 3. Currency Conversion at the daily ECB rate (Nexus is the only market with EUR/GBP listings)
    if 'Currency' in df.columns:
        df['Currency'] = df['Currency'].str.strip()
        df['FX_Rate'] = [usd_per_unit(c, d) for c, d in zip(df['Currency'], df['Date'])]
    else:
        df['FX_Rate'] = 1.0
    df['Price_USD'] = df['Price'] * df['FX_Rate']

    # 4. Actual Category to lowercase
    df['ActualCategory'] = df['ActualCategory'].str.lower()
    df['ActualCategory'] = df['ActualCategory'].replace({'crackedsw': 'crackedsw/tools'})
    
    # 5. Add Marketplace Origin (Section 1.1.3)
    df['_marketplace'] = marketplace_name

    # 6. Cleanup NA values from ProductId
    df = df.dropna(subset=['ProductId'])

    # 7. Normalize Vendor
    df['Vendor'] = df['Vendor'].str.lower().str.strip()
    
    return df

def deduplicate_master(df):
    """
    Rule: ProductId, Date, and ActualCategory (Section 1.1.3)
    """
    initial_count = len(df)
    df = df.drop_duplicates(subset=['ProductId', 'Date', 'ActualCategory'])
    print(f"Deduplication removed {initial_count - len(df)} duplicate records.")
    return df

def run_marketplace_structure_analysis(df):
    """
    Level One descriptive stats for RQ1 (Section 1.1.x)
    """
    # 1. Daily counts of active listings per marketplace
    daily_counts = df.groupby(['Date', '_marketplace']).size().unstack(fill_value=0)
    
    # 2. Category-level distribution (Counts and Percentages)
    cat_dist = df.groupby(['_marketplace', 'ActualCategory']).size().unstack(fill_value=0)
    cat_dist_pct = cat_dist.div(cat_dist.sum(axis=1), axis=0) * 100
    
    # 3. Daily active vendors
    daily_vendors = df.groupby(['Date', '_marketplace'])['Vendor'].nunique().unstack(fill_value=0)
    
    # 4. Correlation: Listings vs. Vendors (Pearson & Spearman)
    # Validates if market growth is driven by new vendors or existing vendor expansion
    corrs = {}
    for market in df['_marketplace'].unique():
        r_p, _ = stats.pearsonr(daily_counts[market], daily_vendors[market])
        r_s, _ = stats.spearmanr(daily_counts[market], daily_vendors[market])
        corrs[market] = {'Pearson': r_p, 'Spearman': r_s}
    
    # 5. Market Concentration (HHI)
    # Assess if the market is dominated by a few 'Super-Vendors'
    hhi_results = {}
    for market in df['_marketplace'].unique():
        v_counts = df[df['_marketplace'] == market].groupby('Vendor').size()
        shares = v_counts / v_counts.sum()
        hhi_results[market] = (shares**2).sum()

    return {
        "daily_listings": daily_counts,
        "category_dist": cat_dist_pct,
        "correlations": pd.DataFrame(corrs).T,
        "concentration_hhi": hhi_results
    }

def calculate_diversity_index(df):
    """Calculates Shannon Entropy (Diversity) for each marketplace (1.4)."""
    diversity_results = {}
    for market in df['_marketplace'].unique():
        market_data = df[df['_marketplace'] == market]
        # Calculate shares of each category
        shares = market_data['ActualCategory'].value_counts(normalize=True)
        # Shannon Entropy Formula: -sum(p * log(p))
        entropy = -1 * (shares * np.log(shares)).sum()
        diversity_results[market] = round(entropy, 3)
    return diversity_results

def get_vendor_concentration(df):
    """Calculates Vendor Activity Distribution (1.8)."""
    # Group by market and vendor to see who is most active
    v_counts = df.groupby(['_marketplace', 'Vendor']).size().reset_index(name='listing_count')
    
    concentration = {}
    for market in df['_marketplace'].unique():
        m_v = v_counts[v_counts['_marketplace'] == market]['listing_count']
        total = m_v.sum()
        # Top 10% of vendors account for what % of listings?
        top_10_percent_count = max(1, int(len(m_v) * 0.1))
        top_10_sum = m_v.sort_values(ascending=False).head(top_10_percent_count).sum()
        concentration[market] = round((top_10_sum / total) * 100, 2)
    return concentration

def calculate_specialization_index(df):
    """
    Calculates Relative Market Specialization (RMS).
    Values > 1.0 indicate a market specializes in that category.
    """
    # Global category distribution
    global_dist = df['ActualCategory'].value_counts(normalize=True)
    
    specialization = {}
    for market in df['_marketplace'].unique():
        market_dist = df[df['_marketplace'] == market]['ActualCategory'].value_counts(normalize=True)
        # RMS = (Market Share) / (Global Share)
        rms = market_dist / global_dist
        specialization[market] = rms.round(2)
        
    return pd.DataFrame(specialization)

LEGIT_TOOL_KEYWORDS = [
    'kali', 'nessus', 'forensic', 'antivirus', 'nmap', 'burp',
    'metasploit', 'cobalt strike', 'wireshark', 'oxygen forensic',
    'elcomsoft', 'accessdata', 'mobiledit', 'eset']

def crackedsw_sensitivity_check(unique_master):
    mask = unique_master['ActualCategory'] == 'crackedsw/tools'  # update name to match your rename
    is_legit = unique_master.loc[mask, 'Title'].str.contains(
        '|'.join(LEGIT_TOOL_KEYWORDS), case=False, na=False)

    share_inclusive = (unique_master['ActualCategory'] == 'malware/exploits').mean() * 100
    excl_master = unique_master.drop(unique_master.loc[mask].index[is_legit.values])
    share_exclusive = (excl_master['ActualCategory'] == 'malware/exploits').mean() * 100

    print(f"Flagged as legit/dual-use: {is_legit.sum()} of {mask.sum()} crackedsw rows")
    print(f"malware/exploits share, inclusive: {share_inclusive:.2f}%")
    print(f"malware/exploits share, excluding flagged tooling: {share_exclusive:.2f}%")
    return is_legit.sum(), share_inclusive, share_exclusive

def run_ecosystem_analysis(df):
    """
    Analyzes multi-homing and product overlap (Section 1.1.1)
    """
    markets = df['_marketplace'].unique()
    
    # --- 3.1 & 3.3 Vendor Overlap & Jaccard ---
    vendor_sets = {m: set(df[df['_marketplace'] == m]['Vendor'].unique()) for m in markets}
    jaccard_matrix = pd.DataFrame(index=markets, columns=markets, dtype=float)
    
    for m1 in markets:
        for m2 in markets:
            u = len(vendor_sets[m1].union(vendor_sets[m2]))
            i = len(vendor_sets[m1].intersection(vendor_sets[m2]))
            jaccard_matrix.loc[m1, m2] = i / u if u > 0 else 0
            
    # --- 3.4 Cross-market price comparison for same titles ---
    # We find titles present in at least 2 markets
    title_counts = df.groupby('Title')['_marketplace'].nunique()
    overlap_titles = title_counts[title_counts > 1].index
    
    # Average price per title per market
    price_comp = df[df['Title'].isin(overlap_titles)].groupby(['Title', '_marketplace'])['Price_USD'].mean().unstack()
    
    # Calculate 'Arbitrage': The price difference between markets for the same item
    price_comp['Price_Range'] = price_comp.max(axis=1) - price_comp.min(axis=1)
    
    return {
        "jaccard_vendors": jaccard_matrix,
        "price_arbitrage": price_comp.sort_values('Price_Range', ascending=False),
        "multi_homing_count": len(title_counts[title_counts > 1])
    }

def calculate_gini(array):
    """Calculates the Gini coefficient for vendor inequality."""
    array = np.array(array, dtype=np.float64)
    if np.amin(array) < 0:
        array -= np.amin(array) # Values must be non-negative
    array += 0.0000001 # Adherence to non-zero mean
    n = array.size
    array = np.sort(array)
    index = np.arange(1, n + 1)
    return ((np.sum((2 * index - n - 1) * array)) / (n * np.sum(array)))

def plot_lorenz_curve(df, market_name):
    # Get vendor listing counts
    v_counts = df[df['_marketplace'] == market_name].groupby('Vendor').size().sort_values().values
    n = len(v_counts)
    
    # Calculate cumulative shares
    cum_listings = np.cumsum(v_counts) / np.sum(v_counts)
    cum_vendors = np.arange(1, n + 1) / n
    
    # Plot
    plt.plot(cum_vendors, cum_listings, label=f"{market_name.capitalize()}")
    plt.plot([0, 1], [0, 1], color='grey', linestyle='--') # Line of Equality

def calculate_shannon_entropy(df, col='ActualCategory'):
    """Calculates Shannon Entropy for category diversity (Axis B)."""
    counts = df[col].value_counts()
    probs = counts / counts.sum()
    return -np.sum(probs * np.log(probs))

def calculate_rms_index(df):
    """
    Calculates Relative Market Specialization (RMS).
    RMS = (Market Share of Category) / (Global Share of Category)
    Values > 1.0 indicate specialization.
    """
    global_dist = df['ActualCategory'].value_counts(normalize=True)
    rms_results = {}
    
    for market in df['_marketplace'].unique():
        market_dist = df[df['_marketplace'] == market]['ActualCategory'].value_counts(normalize=True)
        rms_results[market] = (market_dist / global_dist).round(2)
        
    return pd.DataFrame(rms_results).fillna(0)

def calculate_category_volatility(df):
    """
    Calculates Coefficient of Variation (CV) for category supply.
    CV = Standard Deviation / Mean. 
    Lower CV = More stable/professionalized supply.
    """
    daily_counts = df.groupby(['Date', 'ActualCategory']).size().unstack(fill_value=0)
    # CV per category
    cv = (daily_counts.std() / daily_counts.mean()).round(3)
    return cv.sort_values()


def run_composition_stability_test(df, min_expected=5):
    """
    Performs a Chi-square test to see if category composition changed 
    significantly between the first and second half of the observation period.
    """

    dates = sorted(df['Date'].unique())
    mid_point = dates[len(dates)//2]

    df = df.copy()
    df['Period'] = df['Date'].apply(lambda x: 'First Half' if x < mid_point else 'Second Half')
    contingency_table = pd.crosstab(df['ActualCategory'], df['Period'])

    chi2, p, dof, expected = chi2_contingency(contingency_table)
    n = contingency_table.values.sum()
    cramers_v = np.sqrt(chi2 / (n * (min(contingency_table.shape) - 1)))
    pct_low_cells = (expected < min_expected).mean() * 100

    return {"chi2": chi2, "dof": dof, "p_value": p, "cramers_v": cramers_v,
            "pct_low_cells": pct_low_cells, "table": contingency_table}



def run_significance_tests(df, cat_col='ActualCategory', price_col='Price_USD', market_col='_marketplace'):
    """
    Performs Kruskal-Wallis H-test for each category across markets.
    Identifies if price distributions differ significantly.
    """
    from scipy.stats import kruskal
    
    results = []
    for cat in df[cat_col].unique():
        # Filter for the category and drop NaNs
        cat_data = df[df[cat_col] == cat].dropna(subset=[price_col])
        
        # Create groups for each marketplace
        groups = [cat_data[cat_data[market_col] == m][price_col].values for m in cat_data[market_col].unique()]
        
        # Only test if we have at least 2 markets with data (minimum 5 observations each)
        groups = [g for g in groups if len(g) >= 5]
        
        if len(groups) >= 2:
            stat, p = kruskal(*groups)
            results.append({
                'Category': cat,
                'H-Statistic': round(stat, 2),
                'p-value': p,
                'Significant': p < 0.05
            })
            
    return pd.DataFrame(results).sort_values('p-value')

def calculate_market_premium_index(df):
    """
    Calculates the Market Price Premium Index (Metric 3.x).
    Index > 1.0 means the market is more expensive than the global average for that category.
    """
    global_cat_median = df.groupby('ActualCategory')['Price_USD'].median()
    market_cat_median = df.groupby(['_marketplace', 'ActualCategory'])['Price_USD'].median()
    
    # Premium = (Market Median) / (Global Median)
    premium_index = (market_cat_median / global_cat_median).unstack(level=0)
    return premium_index.round(2)

def analyze_individual_volatility(df):
    df = df.copy()
    df['StableKey'] = (df['_marketplace'] + '::' +
                        df['Vendor'].str.strip().str.lower() + '::' +
                        df['Title'].str.strip().str.lower())
    price_counts = df.groupby('StableKey')['Price_USD'].nunique()
    has_changed = price_counts > 1
    meta = df.groupby('StableKey')['_marketplace'].first()
    vol_df = pd.DataFrame({'has_changed': has_changed, '_marketplace': meta})
    return vol_df.groupby('_marketplace')['has_changed'].mean() * 100


def run_price_significance_tests(df):
    """Kruskal-Wallis H-test for cross-market price differences."""
    results = []
    for cat in df['ActualCategory'].unique():
        groups = [df[(df['ActualCategory'] == cat) & (df['_marketplace'] == m)]['Price_USD'].dropna().values 
                  for m in df['_marketplace'].unique()]
        groups = [g for g in groups if len(g) >= 5]
        if len(groups) >= 2:
            stat, p = kruskal(*groups)
            results.append({'Category': cat, 'H-Stat': stat, 'p-value': p})
    return pd.DataFrame(results)


def calculate_jaccard_with_counts(df, entity_col='Vendor'):
    """
    Computes Jaccard Similarity and absolute overlap counts with 
    robust string normalization (lowercase + strip) to prevent undercounting.
    """
    markets = sorted(df['_marketplace'].unique())
    j_mat = pd.DataFrame(index=markets, columns=markets, dtype=float)
    c_mat = pd.DataFrame(index=markets, columns=markets, dtype=int)

    entity_sets = {}
    for m in markets:
        # Lowercase and strip
        normalized_entities = df[df['_marketplace'] == m][entity_col].astype(str).str.strip().str.lower().unique()
        entity_sets[m] = set(normalized_entities)
    
    for m1 in markets:
        for m2 in markets:
            intersection = entity_sets[m1].intersection(entity_sets[m2])
            union = entity_sets[m1].union(entity_sets[m2])
            
            j_mat.loc[m1, m2] = len(intersection) / len(union) if len(union) > 0 else 0
            c_mat.loc[m1, m2] = int(len(intersection))
            
    return j_mat, c_mat

def get_cross_market_arbitrage(df):
    """
    Identifies same-titled products in multiple markets, calculates price spread,
    and sorts by presence (3 markets first) and then alphabetically by title.
    """
    df = df.copy()
    df['Title'] = df['Title'].astype(str).str.strip().str.lower()  # normalize, matching calculate_jaccard_with_counts

    # 1. Filter for titles that appear in more than one marketplace
    title_counts = df.groupby('Title')['_marketplace'].nunique()
    overlap_titles = title_counts[title_counts > 1].index
    
    # 2. Generate the price pivot table (Mean Price per Title per Marketplace)
    arbitrage = df[df['Title'].isin(overlap_titles)].groupby(['Title', '_marketplace'])['Price_USD'].mean().unstack()
    
    # 3. Identify the marketplace columns for calculation
    market_cols = arbitrage.columns.tolist()
    
    # 4. Calculate Arbitrage Ratio (Max Price / Min Price) 
    # This tells us the magnitude of the price spread across the ecosystem
    arbitrage['Arbitrage_Ratio'] = (arbitrage[market_cols].max(axis=1) / arbitrage[market_cols].min(axis=1)).round(2)
    
    # 5. Calculate Market Presence (how many markets the product is active in)
    arbitrage['Presence'] = arbitrage[market_cols].notna().sum(axis=1)
    
    # 6. Sort by Presence (3 markets first, then 2) and then by Title
    return arbitrage.sort_values(by=['Presence', 'Title'], ascending=[False, True])

def run_posthoc_dunn(df, val_col='Price_USD', group_col='_marketplace'):
    """
    Performs Dunn's post-hoc test with Holm correction.
    Returns a list of pairs that are statistically significant (p < 0.05).
    """
    # 1. Perform the test
    # This returns a matrix of p-values
    p_matrix = sp.posthoc_dunn(df, val_col=val_col, group_col=group_col, p_adjust='holm')
    
    # 2. Extract significant pairs
    significant_pairs = []
    markets = p_matrix.columns
    
    for i in range(len(markets)):
        for j in range(i + 1, len(markets)):
            p_val = p_matrix.iloc[i, j]
            if p_val < 0.05:
                significant_pairs.append(f"{markets[i]} vs {markets[j]} (p={p_val:.4f})")
                
    return significant_pairs

def classify_vendor_pricing_rigidity(master_df, unique_df):
    multi_vendors = unique_df.groupby('Vendor')['_marketplace'].nunique()
    multi_vendors = multi_vendors[multi_vendors > 1].index

    cross = master_df.groupby(['Title','Vendor'])['_marketplace'].nunique().reset_index(name='n_markets')
    cross = cross[(cross['n_markets'] > 1) & (cross['Vendor'].isin(multi_vendors))]

    price_range = master_df.groupby(['Title','Vendor'])['Price_USD'].agg(['min','max']).reset_index()
    merged = cross.merge(price_range, on=['Title','Vendor'])
    merged['rigid'] = merged['min'] == merged['max']

    by_vendor = merged.groupby('Vendor')['rigid'].agg(N='count', N_rigid='sum')
    by_vendor['pct_rigid'] = (by_vendor['N_rigid'] / by_vendor['N'] * 100).round(1)
    return by_vendor.sort_values('pct_rigid', ascending=False), merged

def test_multihoming_vendor_scale(unique_df):
    from scipy.stats import mannwhitneyu
    vendor_markets = unique_df.groupby('Vendor')['_marketplace'].nunique()
    vendor_listings = unique_df.groupby('Vendor').size()

    multi = vendor_listings[vendor_markets[vendor_markets > 1].index]
    single = vendor_listings[vendor_markets[vendor_markets == 1].index]

    stat, p = mannwhitneyu(multi, single, alternative='greater')
    return {
        'multi_n': len(multi), 'multi_median': multi.median(), 'multi_mean': multi.mean(),
        'single_n': len(single), 'single_median': single.median(), 'single_mean': single.mean(),
        'U': stat, 'p': p
    }

# =====================================================================
# STEP 2.1  Uncertainty for the specialization index (RMS) and Shannon
# =====================================================================
# Listings are not independent: one vendor often supplies most of a small
# category. The bootstrap therefore resamples whole vendors (with all their
# listings) within each market, recomputes the index, and repeats this
# n_boot times. The middle 95% of those values is the confidence interval.

def _resample_vendors(unique_df, rng):
    parts = []
    for market, g in unique_df.groupby('_marketplace'):
        vendors = g['Vendor'].unique()
        pick = rng.choice(vendors, size=len(vendors), replace=True)
        by_vendor = {v: grp for v, grp in g.groupby('Vendor')}
        parts += [by_vendor[v] for v in pick]
    return pd.concat(parts)

def rms_with_vendor_ci(unique_df, n_boot=2000, seed=2025):
    """RMS per category x market with a 95% vendor-bootstrap interval,
    plus the number of listings and vendors behind each value."""
    rng = np.random.default_rng(seed)
    point = calculate_rms_index(unique_df).replace(0, np.nan)
    boots = []
    for _ in range(n_boot):
        b = calculate_rms_index(_resample_vendors(unique_df, rng)).replace(0, np.nan)
        boots.append(b.reindex(index=point.index, columns=point.columns))
    arr = np.stack([b.values for b in boots])
    import warnings
    with warnings.catch_warnings():          # categories absent from a market give all-NaN cells
        warnings.simplefilter('ignore', RuntimeWarning)
        lo = pd.DataFrame(np.nanpercentile(arr, 2.5, axis=0), index=point.index, columns=point.columns)
        hi = pd.DataFrame(np.nanpercentile(arr, 97.5, axis=0), index=point.index, columns=point.columns)
    n_list = unique_df.groupby(['ActualCategory', '_marketplace']).size().unstack()
    n_vend = unique_df.groupby(['ActualCategory', '_marketplace'])['Vendor'].nunique().unstack()
    rows = []
    for cat in point.index:
        for m in point.columns:
            if pd.isna(point.loc[cat, m]):
                continue
            rows.append({'Category': cat, 'Market': m, 'RMS': round(point.loc[cat, m], 2),
                         'CI_low': round(lo.loc[cat, m], 2), 'CI_high': round(hi.loc[cat, m], 2),
                         'Listings': int(n_list.loc[cat, m]), 'Vendors': int(n_vend.loc[cat, m]),
                         'Clearly_above_1': lo.loc[cat, m] > 1, 'Clearly_below_1': hi.loc[cat, m] < 1})
    return pd.DataFrame(rows)

def shannon_with_vendor_ci(unique_df, n_boot=2000, seed=2025):
    """Shannon diversity per market with a 95% vendor-bootstrap interval."""
    rng = np.random.default_rng(seed)
    markets = sorted(unique_df['_marketplace'].unique())
    point = {m: calculate_shannon_entropy(unique_df[unique_df['_marketplace'] == m]) for m in markets}
    boots = {m: [] for m in markets}
    for _ in range(n_boot):
        b = _resample_vendors(unique_df, rng)
        for m in markets:
            boots[m].append(calculate_shannon_entropy(b[b['_marketplace'] == m]))
    return pd.DataFrame({'H': point,
                         'CI_low': {m: np.percentile(boots[m], 2.5) for m in markets},
                         'CI_high': {m: np.percentile(boots[m], 97.5) for m in markets}}).round(3)

def composition_by_native_section(unique_df):
    """Unique listings per coded category within each scraped marketplace section.
    Shows which category shares come from sections that only one market had scraped."""
    return (unique_df.groupby(['_marketplace', 'Category', 'ActualCategory']).size()
            .unstack(fill_value=0))


# =====================================================================
# STEP 2.2  Which products really changed price?
# =====================================================================
# The thesis rule ("more than one distinct Price_USD value per product") counts
# three things that are not a vendor changing the price:
#   (a) two listings with the same vendor+title on the same day at different prices
#       (they share one StableKey, so they look like one product with two prices);
#   (b) currency conversion: a EUR price converted at a different daily rate gives a
#       different USD value although the vendor changed nothing (a vendor switching a
#       listing from EUR to USD, on the other hand, IS a real change and is counted);
#   (c) Abacus displays USD prices that it converts itself from a base (EUR-like)
#       price at every visit, so the shown USD price moves with the exchange rate.
# The functions below remove all three.

def _stable_key(df):
    return (df['_marketplace'] + '::' + df['Vendor'].astype(str).str.strip().str.lower() + '::' +
            df['Title'].astype(str).str.strip().str.lower())

def detect_platform_reconversion(df, market='abacus', tol=0.01):
    """
    Finds listings whose displayed price only moves because the platform re-converts it.
    Model: log(price) = listing's base price + a factor shared by all listings on that date.
    A listing is 're-converted' if, after removing the shared daily factor, its base price
    never moves by more than `tol` (1%). Returns (set of ProductIds, daily factor series).
    """
    m = df[df['_marketplace'] == market]
    moving = m.groupby('ProductId')['Price'].nunique()
    x = m[m['ProductId'].isin(moving[moving > 1].index)].copy()
    if x.empty:
        return set(), pd.Series(dtype=float)
    x['lp'] = np.log(x['Price'])
    base = x.groupby('ProductId')['lp'].median()
    for _ in range(50):                      # alternate: daily factor <-> base prices
        daily = (x['lp'] - x['ProductId'].map(base)).groupby(x['Date']).median()
        base = (x['lp'] - x['Date'].map(daily)).groupby(x['ProductId']).median()
    x['base'] = x['lp'] - x['Date'].map(daily)
    jump = x.sort_values('Date').groupby('ProductId')['base'].diff().abs().groupby(x['ProductId']).max()
    return set(jump[jump <= tol].index), np.exp(daily)

def _changed(df, price_col, key_col, currency_col=None):
    """True per key if its set of prices differs between dates (simultaneous duplicates ignored).
    With currency_col, a price is the pair (currency, amount), so switching a listing from
    EUR 5.99 to USD 3.99 counts as a change, while a constant EUR price does not."""
    d = df.copy()
    if currency_col is None:
        d['_pt'] = d[price_col].round(2).astype(str)
    else:
        d['_pt'] = d[currency_col].astype(str) + ' ' + d[price_col].round(2).astype(str)
    per_day = d.groupby([key_col, 'Date'])['_pt'].apply(lambda s: tuple(sorted(s.unique())))
    return per_day.groupby(level=0).nunique() > 1

def _own_price(d):
    """Listed price in its own currency; Abacus listings that the platform re-converts get a constant marker."""
    reconv, _ = detect_platform_reconversion(d, 'abacus')
    is_rc = d['ProductId'].isin(reconv) & (d['_marketplace'] == 'abacus')
    return np.where(is_rc, -1.0, d['Price'])

def price_change_flags(df):
    """
    One row per unique product (StableKey) with:
      changed_thesis_rule  - old rule (distinct Price_USD values)
      changed              - corrected rule: price in its own currency (a currency switch counts),
                             compared between dates, without Abacus platform re-conversion
    """
    d = df.copy()
    d['StableKey'] = _stable_key(d)
    d['p'] = _own_price(d)
    old = d.groupby('StableKey')['Price_USD'].nunique() > 1
    new = _changed(d, 'p', 'StableKey', currency_col='Currency')
    meta = d.groupby('StableKey')[['_marketplace', 'ActualCategory', 'Vendor']].first()
    switched = d.groupby('StableKey')['Currency'].nunique() > 1
    return (meta.join(old.rename('changed_thesis_rule')).join(new.rename('changed'))
                .join(switched.rename('currency_switch')))

def price_change_breakdown(df):
    """Share of products with a price change per market, removing one artefact at a time."""
    d = df.copy()
    d['StableKey'] = _stable_key(d)
    d['p'] = _own_price(d)
    steps = {
        '1_thesis_rule': d.groupby('StableKey')['Price_USD'].nunique() > 1,
        '2_between_dates_only': _changed(d, 'Price_USD', 'StableKey'),
        '3_own_currency': _changed(d, 'Price', 'StableKey', currency_col='Currency'),
        '4_without_abacus_reconversion': _changed(d, 'p', 'StableKey', currency_col='Currency'),
    }
    market = d.groupby('StableKey')['_marketplace'].first()
    out = pd.DataFrame({k: v.groupby(market).mean() * 100 for k, v in steps.items()})
    out.loc['all'] = [v.mean() * 100 for v in steps.values()]
    counts = pd.DataFrame({k: v.groupby(market).sum() for k, v in steps.items()})
    counts.loc['all'] = [v.sum() for v in steps.values()]
    return out.round(2), counts


# =====================================================================
# STEP 2.3  Price differences between markets, tested at vendor level
# =====================================================================
# Kruskal-Wallis assumes independent observations. Listings are not: one vendor
# often posts many similar products at similar prices, so 40 listings from one
# vendor count as 40 "votes" for that vendor's price level. Two remedies:
#   (1) vendor medians: one value per vendor per market, then Kruskal-Wallis
#       (main result; simple to report);
#   (2) cluster permutation: keep the listing-level H statistic, but judge it
#       against market labels shuffled between whole vendor catalogues
#       (robustness check).

def _dunn_holm_pairs(values, groups, alpha=0.05):
    """Dunn's test with Holm correction (tie-corrected); returns significant pairs like 'A-N'."""
    values = np.asarray(values, float); groups = np.asarray(groups)
    ranks = stats.rankdata(values); n = len(values)
    _, ties = np.unique(values, return_counts=True)
    s2 = n * (n + 1) / 12 - (ties ** 3 - ties).sum() / (12 * (n - 1))
    labels = sorted(set(groups)); res = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = groups == labels[i], groups == labels[j]
            z = (ranks[a].mean() - ranks[b].mean()) / np.sqrt(s2 * (1 / a.sum() + 1 / b.sum()))
            res.append((labels[i][0].upper() + '-' + labels[j][0].upper(), 2 * stats.norm.sf(abs(z))))
    order = np.argsort([p for _, p in res]); k = len(res); adj = [0.0] * k; running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (k - rank) * res[idx][1])); adj[idx] = running
    sig = [res[i][0] for i in range(k) if adj[i] < alpha]
    return 'All' if k == 3 and len(sig) == 3 else (', '.join(sig) if sig else 'None')

def kruskal_listing_and_vendor_level(unique_df, price_col='Price_USD', n_perm=2000, seed=2025):
    """Table 4 with three versions of the cross-market test per category."""
    rng = np.random.default_rng(seed)
    rows = []
    for cat in sorted(unique_df['ActualCategory'].unique()):
        cd = unique_df[unique_df['ActualCategory'] == cat]
        if cd['_marketplace'].nunique() < 2:
            continue
        n = len(cd)
        H, p = stats.kruskal(*[g[price_col].values for _, g in cd.groupby('_marketplace')])
        # (1) vendor medians
        vm = cd.groupby(['_marketplace', 'Vendor'])[price_col].median().reset_index()
        nv = len(vm)
        if vm[price_col].nunique() > 1:
            Hv, pv = stats.kruskal(*[g[price_col].values for _, g in vm.groupby('_marketplace')])
            pairs_v = _dunn_holm_pairs(vm[price_col].values, vm['_marketplace'].values)
        else:
            Hv, pv, pairs_v = 0.0, 1.0, 'None'
        # (2) cluster permutation
        clusters = [(m, g[price_col].values) for (m, v), g in cd.groupby(['_marketplace', 'Vendor'])]
        labels = np.array([m for m, _ in clusters]); sizes = np.array([len(v) for _, v in clusters])
        flat = np.concatenate([v for _, v in clusters])
        exceed = 0
        for _ in range(n_perm):
            lab = np.repeat(rng.permutation(labels), sizes)
            grp = [flat[lab == m] for m in np.unique(lab)]
            exceed += stats.kruskal(*grp)[0] >= H - 1e-9
        rows.append({
            'Category': cat, 'N listings': n, 'Vendors A/N/V': '/'.join(
                str(int((vm['_marketplace'] == m).sum())) for m in ['abacus', 'nexus', 'vortex']),
            'H (listings)': round(H, 2), 'p (listings)': float(f'{p:.3g}'),
            'eps2 (listings)': round(H / ((n ** 2 - 1) / (n + 1)), 3),
            'Pairs (listings)': _dunn_holm_pairs(cd[price_col].values, cd['_marketplace'].values),
            'H (vendor medians)': round(Hv, 2), 'p (vendor medians)': float(f'{pv:.3g}'),
            'eps2 (vendor medians)': round(Hv / ((nv ** 2 - 1) / (nv + 1)), 3),
            'Pairs (vendor medians)': pairs_v,
            'p (cluster permutation)': round((1 + exceed) / (n_perm + 1), 4),
        })
    return pd.DataFrame(rows)


# =====================================================================
# STEP 2.4  Cross-market pricing (RQ4): same vendor, own currency
# =====================================================================
# Two problems in the original RQ4 pricing tables:
#   (1) a title was compared across markets even when different vendors sold it,
#       so the 'arbitrage ratio' mixed vendors (e.g. SpyNote: sacky $4, trio $20);
#   (2) 'same price' was judged in USD. A EUR listing converted at the daily rate never
#       equals a USD listing, and Abacus re-converts some prices itself, so these always
#       looked 'variable' although the vendor set one fixed price.
# Fix: compare the same vendor + title, and look for a price point that is identical in the
# currency it was actually set in (EUR for Nexus EUR listings and for Abacus listings that
# the platform re-converts; USD otherwise), allowing 1% for rounding.

def _norm_title(s):
    return s.astype(str).str.strip().str.lower()

def own_currency_price_points(master, tol_reconv=0.01):
    """Adds Price_own / Currency_own: the price in the currency the vendor set it in.
    Abacus listings that the platform re-converts get their EUR price (USD shown / ECB rate)."""
    d = master.copy()
    reconv, _ = detect_platform_reconversion(d, 'abacus', tol=tol_reconv)
    is_rc = (d['_marketplace'] == 'abacus') & d['ProductId'].isin(reconv)
    eur = d['Price'] / [usd_per_unit('EUR', x.date() if hasattr(x, 'date') else x) for x in d['Date']]
    eur_med = eur.where(is_rc).groupby(d['ProductId']).transform('median')
    d['Price_own'] = np.where(is_rc, eur_med.round(2), d['Price'])
    d['Currency_own'] = np.where(is_rc, 'EUR', d['Currency'])
    return d

def cross_market_vendor_titles(master, tol=0.01):
    """
    Every vendor + title (normalized) listed on more than one market, with the price points per
    market in own currency and whether one identical price point exists on all its markets.
    """
    d = own_currency_price_points(master)
    d['t'] = _norm_title(d['Title'])
    n_mk = d.groupby(['Vendor', 't'])['_marketplace'].nunique()
    pairs = n_mk[n_mk > 1].index
    rows = []
    for (v, t) in pairs:
        g = d[(d['Vendor'] == v) & (d['t'] == t)]
        pts = {m: set(zip(h['Currency_own'], h['Price_own'].round(2))) for m, h in g.groupby('_marketplace')}
        mk = sorted(pts)
        common = [f'{c} {p:.2f}' for c, p in pts[mk[0]]
                  if all(any(c2 == c and abs(p2 / p - 1) <= tol for c2, p2 in pts[o]) for o in mk[1:])]
        usd = g.groupby('_marketplace')['Price_USD'].mean()
        rows.append({
            'Vendor': v, 'Title': g['Title'].iloc[0][:60], 'Markets': 'all' if len(mk) == 3 else ', '.join(mk),
            'Prices (own currency)': '; '.join(f"{m}: " + ', '.join(f'{c} {p:.2f}' for c, p in sorted(pts[m])) for m in mk),
            'Rigid (same price on every market)': bool(common),
            'Common price': common[0] if common else '',
            'Switched EUR to USD on Nexus': g[g['_marketplace'] == 'nexus']['Currency'].nunique() > 1,
            'USD min (ECB)': round(g['Price_USD'].min(), 2), 'USD max (ECB)': round(g['Price_USD'].max(), 2),
            'Ratio of market means (USD)': round(usd.max() / usd.min(), 2),
        })
    return pd.DataFrame(rows)

def rigidity_by_vendor(pairs_df):
    """Table 7: per vendor, how many cross-market titles keep one identical price."""
    t = pairs_df.groupby('Vendor').agg(
        Pairs=('Title', 'size'), Rigid=('Rigid (same price on every market)', 'sum'),
        Switched_EUR_to_USD_on_Nexus=('Switched EUR to USD on Nexus', 'sum'))
    t['Rigid %'] = (t['Rigid'] / t['Pairs'] * 100).round(1)
    return t.sort_values(['Pairs', 'Rigid %'], ascending=False)

def arbitrage_by_vendor(master, presence=3):
    """Table 6, split by vendor: mean price per market of each title present on `presence` markets."""
    d = own_currency_price_points(master)
    d['t'] = _norm_title(d['Title'])
    pres = d.groupby('t')['_marketplace'].nunique()
    sel = d[d['t'].isin(pres[pres >= presence].index)]
    out = sel.groupby(['t', 'Vendor', '_marketplace']).agg(
        price=('Price_own', 'mean'), cur=('Currency_own', 'first')).reset_index()
    out['price'] = out['price'].round(2).astype(str) + ' ' + out['cur']
    tab = out.pivot_table(index=['t', 'Vendor'], columns='_marketplace', values='price', aggfunc='first')
    return tab.fillna('')