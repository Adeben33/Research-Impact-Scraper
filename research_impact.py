import pandas as pd
import requests
import time
import logging
import os
from scholarly import scholarly
import re

# ---------- CONFIG ----------
UNPAYWALL_EMAIL = "adeniyiebenezer33@gmail.com"
DEBUG_MODE = True

# ---------- LOGGING ----------
logging.basicConfig(
    filename='research_impact_log.txt',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ---------- DOI + PMID HELPERS ----------
def clean_doi(doi):
    if not doi:
        return None
    if doi.startswith("https://doi.org/"):
        return doi.replace("https://doi.org/", "")
    if "doi.org" not in doi:
        return None
    return doi

def query_doi_from_openalex(title, author=None):
    title_clean = re.sub(r'[^\w\s]', '', title.lower())[:200]
    query = f"title.search:{title_clean}"
    if author:
        query += f" AND author.display_name.search:{author}"
    url = f"https://api.openalex.org/works?filter={query}&per-page=1"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                work = results[0]
                return work.get("doi", "").replace("https://doi.org/", ""), work.get("ids", {}).get("pmid")
    except Exception as e:
        logging.warning(f"OpenAlex DOI lookup failed for '{title}': {e}")
    return None, None

def query_doi_from_crossref(title):
    url = f"https://api.crossref.org/works?query.title={requests.utils.quote(title)}&rows=1"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            items = r.json()["message"].get("items", [])
            if items:
                return items[0].get("DOI"), None
    except Exception as e:
        logging.warning(f"Crossref DOI lookup failed for '{title}': {e}")
    return None, None

def get_pmid_from_pubmed(title):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "retmode": "json",
        "term": title
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        return ids[0] if ids else None
    except Exception as e:
        logging.warning(f"PubMed PMID lookup failed for '{title}': {e}")
    return None

# ---------- ALTMETRIC & OA ----------
def get_altmetric_summary(doi, pmid=None, title=None, altmetric_404_log=None):
    url = f"https://api.altmetric.com/v1/doi/{doi}"
    try:
        r = requests.get(url)
        if DEBUG_MODE:
            print(f"\U0001F517 Altmetric URL: {url} — Status: {r.status_code}")
        if r.status_code == 200:
            return extract_altmetric_data(r.json())
        elif r.status_code == 404:
            if title and altmetric_404_log is not None:
                altmetric_404_log.append(title)
            return get_altmetric_by_pmid(pmid) if pmid else None
    except Exception as e:
        logging.error(f"Altmetric error for DOI {doi}: {e}")
    return None

def get_altmetric_by_pmid(pmid):
    url = f"https://api.altmetric.com/v1/pmid/{pmid}"
    try:
        r = requests.get(url)
        if DEBUG_MODE:
            print(f"\U0001F517 Altmetric PMID URL: {url} — Status: {r.status_code}")
        if r.status_code == 200:
            return extract_altmetric_data(r.json())
    except Exception as e:
        logging.error(f"Altmetric error for PMID {pmid}: {e}")
    return None

def extract_altmetric_data(data):
    return {
        "altmetric_id": data.get("id"),
        "score": data.get("score", 0),
        "counts": {
            'Twitter': data.get('cited_by_tweeters_count', 0),
            'Reddit': data.get('cited_by_rdts_count', 0),
            'Blogs': data.get('cited_by_feeds_count', 0),
            'News': data.get('cited_by_msm_count', 0),
            'Facebook': data.get('cited_by_fbwalls_count', 0),
            'Wikipedia': data.get('cited_by_wikipedia_count', 0),
            'Policy Docs': data.get('cited_by_policy_count', 0)
        }
    }

def get_open_access_status(doi):
    url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
    try:
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            return data.get("is_oa", False), data.get("oa_status", "unknown")
    except Exception as e:
        logging.error(f"Unpaywall error for DOI {doi}: {e}")
    return None, None

# ---------- OTHER HELPERS ----------
def tag_keywords(text, keyword_list):
    return any(k in text.lower() for k in keyword_list)

def has_media_mentions(altmetric):
    if not altmetric:
        return False
    counts = altmetric.get("counts", {})
    return any(counts.get(k, 0) > 0 for k in ['News', 'Blogs', 'Policy Docs', 'Facebook', 'Wikipedia'])

# ---------- GOOGLE SCHOLAR ----------
def get_author_by_user_id(user_id):
    try:
        author = scholarly.search_author_id(user_id)
        filled = scholarly.fill(author)
        return filled, filled['name']
    except Exception as e:
        logging.error(f"Error fetching scholar profile for user ID {user_id}: {e}")
    return None, None

def get_scholar_publications(filled_author, max_results=300):
    publications = []
    for pub in filled_author.get('publications', [])[:max_results]:
        try:
            detailed = scholarly.fill(pub)
            publications.append(detailed)
            time.sleep(1)
        except Exception as e:
            logging.warning(f"Failed to fill publication: {e}")
    return publications

# ---------- MAIN PROCESS ----------
def process_author(author_name, user_id):
    logging.info(f"\U0001F50D Starting collection for {author_name} (ID: {user_id})")
    author_profile, _ = get_author_by_user_id(user_id)
    if not author_profile:
        print(f"❌ No Google Scholar profile found for: {author_name}")
        return

    altmetric_404_titles = []

    profile_metrics = {
        "Author": author_name,
        "Citations_All": author_profile.get("citedby", 0),
        "Citations_Since2020": author_profile.get("citedby5y", 0),
        "h_index_All": author_profile.get("hindex", 0),
        "h_index_Since2020": author_profile.get("hindex5y", 0),
        "i10_index_All": author_profile.get("i10index", 0),
        "i10_index_Since2020": author_profile.get("i10index5y", 0)
    }
    os.makedirs("csv", exist_ok=True)
    pd.DataFrame([profile_metrics]).to_csv(f"csv/{author_name.lower().replace(' ', '_')}_metrics.csv", index=False)

    works = get_scholar_publications(author_profile)
    results = []

    for work in works:
        title = work['bib'].get("title", "Untitled")
        year = work['bib'].get("pub_year", "N/A")
        citations = work.get("num_citations", 0)
        authors = work['bib'].get("author", "")
        venue = work['bib'].get("venue", "N/A")
        raw_doi = work.get("pub_url", "")
        doi = clean_doi(raw_doi)

        pmid = None
        if not doi:
            doi, pmid = query_doi_from_openalex(title, author_name)
            if not doi:
                doi, _ = query_doi_from_crossref(title)
        if not pmid:
            pmid = get_pmid_from_pubmed(title)

        if not doi and not pmid:
            logging.info(f"❌ Skipping — No DOI or PMID found for: {title}")
            continue

        print(f"\U0001F4C4 Processing: {title} ({doi if doi else 'No DOI'})")
        altmetric = get_altmetric_summary(doi, pmid, title=title, altmetric_404_log=altmetric_404_titles)
        media_flag = has_media_mentions(altmetric)
        counts = altmetric.get("counts", {}) if altmetric else {}
        oa_flag, oa_status = get_open_access_status(doi) if doi else (None, None)

        results.append({
            "Author": author_name,
            "Paper Title": title,
            "Year": year,
            "Publication Type": "Published",
            "Citations": citations,
            "DOI": f"https://doi.org/{doi}" if doi else "N/A",
            "PMID": pmid,
            "Authors": authors,
            "Journal": venue,
            "Altmetric Score": altmetric.get("score") if altmetric else "Not Available",
            "Twitter Mentions": counts.get("Twitter", 0),
            "Reddit Mentions": counts.get("Reddit", 0),
            "News Mentions": counts.get("News", 0),
            "Blog Mentions": counts.get("Blogs", 0),
            "Facebook Mentions": counts.get("Facebook", 0),
            "Wikipedia Mentions": counts.get("Wikipedia", 0),
            "Policy Mentions": counts.get("Policy Docs", 0),
            "Media Mentioned": media_flag,
            "Open Access": oa_flag,
            "OA Status": oa_status,
            "Public Health Impact": tag_keywords(title, public_health_keywords),
            "Capacity Building": tag_keywords(title, capacity_building_keywords)
        })
        time.sleep(2)

    if results:
        df = pd.DataFrame(results)
        safe_name = author_name.lower().replace(' ', '_')
        os.makedirs("json", exist_ok=True)
        df.to_csv(f"csv/{safe_name}_impact_metrics.csv", index=False)
        df.to_json(f"json/{safe_name}_impact_metrics.json", orient="records", indent=2)
        print(f"✅ Finished for {author_name} — {len(results)} papers saved.")

    if altmetric_404_titles:
        pd.DataFrame(altmetric_404_titles, columns=["Title"]).to_csv(
            f"csv/{author_name.lower().replace(' ', '_')}_altmetric_404.csv", index=False
        )
        print(f"⚠️ {len(altmetric_404_titles)} papers returned Altmetric 404. Saved to CSV.")

# ---------- KEYWORDS ----------
public_health_keywords = [
    "public health", "infectious disease", "epidemiology", "mathematical modeling",
    "COVID-19", "cholera", "malaria", "pandemic", "outbreak", "disease mitigation",
    "early warning systems", "community response", "health systems", "health equity",
    "vaccination", "surveillance", "data-driven decision-making", "risk communication",
    "contact tracing", "behavior change", "public engagement", "intervention", "awareness"
]

capacity_building_keywords = [
    "training", "capacity", "leadership", "sustainability", "skills development", "education",
    "data science training", "epidemiological training", "south-south collaboration",
    "research network", "mentorship", "interdisciplinary teams", "technology transfer",
    "local expertise", "workforce development", "collaborative learning",
    "public health training", "AI and data innovation", "institutional strengthening", "infrastructure building"
]

# ---------- AUTHOR DICTIONARY ----------
author_dict = {
    "Jude Kong": "dPAVmL0AAAAJ",
    # "Another Author": "xxxxxxxxxxx",
}

# ---------- EXECUTION ----------
for author_name, user_id in author_dict.items():
    process_author(author_name, user_id)

print("\U0001F389 All authors processed. Check your output and log files.")
