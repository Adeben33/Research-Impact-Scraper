import pandas as pd
import requests
import time
import urllib.parse
import logging

# ---------- CONFIG ----------
UNPAYWALL_EMAIL = "adeniyiebenezer33@gmail.com"

# ---------- LOGGING ----------
logging.basicConfig(
    filename='research_impact_log.txt',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ---------- EXPANDED KEYWORDS ----------
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

# ---------- HELPER FUNCTIONS ----------
def search_semantic_scholar_authors(name, max_results=10):
    query = urllib.parse.quote(name)
    url = f"https://api.semanticscholar.org/graph/v1/author/search?query={query}&limit={max_results}&fields=name,paperCount,citationCount"
    r = requests.get(url)
    if r.status_code == 200:
        return r.json().get("data", [])
    return []

def fetch_all_papers_via_next_url(author_id, max_pages=10):
    base_url = f"https://api.semanticscholar.org/graph/v1/author/{author_id}/papers"
    fields = "title,year,authors,externalIds,citationCount,venue,fieldsOfStudy,paperId"
    url = f"{base_url}?limit=100&fields={fields}"
    papers = []
    page_count = 0

    while url and isinstance(url, str) and url.startswith("http") and page_count < max_pages:
        response = requests.get(url)
        if response.status_code != 200:
            logging.warning(f"Request failed at page {page_count + 1}. Status: {response.status_code}")
            break
        result = response.json()
        papers.extend(result.get("data", []))
        url = result.get("next", None)
        page_count += 1
        time.sleep(1)

    return papers

def get_altmetric_summary(doi):
    url = f"https://api.altmetric.com/v1/doi/{doi}"
    try:
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
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
    except Exception as e:
        logging.error(f"Altmetric error for DOI {doi}: {e}")
    return None

def get_altmetric_sources(altmetric_id):
    url = f"https://api.altmetric.com/v1/id/{altmetric_id}"
    try:
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            posts = data.get("posts", [])
            return [post.get("url") for post in posts if "url" in post][:10]
    except Exception as e:
        logging.error(f"Source retrieval error for altmetric ID {altmetric_id}: {e}")
    return []

def get_open_access_status(doi):
    if doi == "Not found":
        return None, None
    url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
    try:
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            return data.get("is_oa", False), data.get("oa_status", "unknown")
    except Exception as e:
        logging.error(f"Unpaywall error for DOI {doi}: {e}")
    return None, None

def tag_keywords(text, keyword_list):
    text = text.lower()
    return any(k in text for k in keyword_list)

def get_doi_from_crossref(title):
    query = urllib.parse.quote(title)
    url = f"https://api.crossref.org/works?query.title={query}&rows=1"
    try:
        r = requests.get(url)
        if r.status_code == 200:
            items = r.json().get("message", {}).get("items", [])
            if items:
                return items[0].get("DOI", None)
    except Exception as e:
        logging.error(f"Crossref error: {e}")
    return None

# ---------- MAIN PROCESSING FUNCTION ----------
def process_author(search_name):
    logging.info(f"Started data collection for: {search_name}")
    authors = search_semantic_scholar_authors(search_name)
    results = []

    if not authors:
        logging.warning(f"No authors found for: {search_name}")
        print(f"❌ No authors found for: {search_name}")
        return

    for author in authors:
        author_id = author["authorId"]
        author_name = author["name"]
        logging.info(f"Fetching papers for: {author_name} (ID: {author_id})")
        papers = fetch_all_papers_via_next_url(author_id)
        logging.info(f"Retrieved {len(papers)} papers for {author_name}")

        for paper in papers:
            title = paper.get("title", "Untitled")
            year = paper.get("year", "N/A")
            citations = paper.get("citationCount", 0)
            authors_list = [a['name'] for a in paper.get("authors", [])]
            doi = paper.get("externalIds", {}).get("DOI", "Not found")
            if doi == "Not found":
                doi = get_doi_from_crossref(title)
                if doi:
                    logging.info(f"Found DOI via Crossref for: {title}")
                else:
                    logging.warning(f"Still missing DOI for: {title}")
                    continue

            venue = paper.get("venue", "N/A")
            fields = paper.get("fieldsOfStudy", [])
            fields_str = "; ".join(fields) if isinstance(fields, list) else str(fields)

            altmetric = get_altmetric_summary(doi)
            altmetric_id = altmetric.get("altmetric_id") if altmetric else None
            sources = get_altmetric_sources(altmetric_id) if altmetric_id else []
            oa_flag, oa_status = get_open_access_status(doi)

            results.append({
                "Author": author_name,
                "Paper Title": title,
                "Year": year,
                "Citations": citations,
                "DOI": doi,
                "Authors": "; ".join(authors_list),
                "Journal": venue,
                "Fields": fields_str,
                "Altmetric Score": altmetric.get("score", 0) if altmetric else 0,
                "Twitter Mentions": altmetric.get("counts", {}).get("Twitter", 0) if altmetric else 0,
                "Reddit Mentions": altmetric.get("counts", {}).get("Reddit", 0) if altmetric else 0,
                "News Mentions": altmetric.get("counts", {}).get("News", 0) if altmetric else 0,
                "Policy Mentions": altmetric.get("counts", {}).get("Policy Docs", 0) if altmetric else 0,
                "Mention URLs": "; ".join(sources),
                "Open Access": oa_flag,
                "OA Status": oa_status,
                "Public Health Impact": tag_keywords(title, public_health_keywords),
                "Capacity Building": tag_keywords(title, capacity_building_keywords)
            })
            time.sleep(1)

    if results:
        df = pd.DataFrame(results)
        df = df.drop_duplicates(subset="DOI")

        safe_name = search_name.lower().replace(' ', '_')
        csv_filename = f"{safe_name}_impact_metrics.csv"
        json_filename = f"{safe_name}_impact_metrics.json"

        df.to_csv(csv_filename, index=False)
        df.to_json(json_filename, orient="records")

        logging.info(f"✅ Saved data for {search_name} to {csv_filename} and {json_filename}")
        print(f"✅ Done for {search_name} → {csv_filename}")
    else:
        logging.warning(f"No valid papers found for {search_name}")
        print(f"⚠️ No valid papers found for {search_name}")

# ---------- MULTIPLE AUTHOR LOOP ----------
author_list = [
    "Jude Kong",
    "Nicola L. Bragazzi"
]

for name in author_list:
    process_author(name)

print("🎉 All authors processed. Check the output files and logs.")
