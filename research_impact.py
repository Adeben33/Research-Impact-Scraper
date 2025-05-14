import pandas as pd
import requests
import time
import urllib.parse
import logging
import os

# ---------- CONFIG ----------
UNPAYWALL_EMAIL = "adeniyiebenezer33@gmail.com"

# ---------- LOGGING ----------
logging.basicConfig(
    filename='research_impact_log.txt',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

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

# ---------- HELPER FUNCTIONS ----------
def search_openalex_author_id(name):
    query = urllib.parse.quote(name)
    url = f"https://api.openalex.org/authors?search={query}"
    r = requests.get(url)
    if r.status_code == 200:
        data = r.json()
        if data.get("results"):
            return data["results"][0]["id"], data["results"][0]["display_name"]
    return None, None

def get_openalex_author_works(author_id, max_results=1000):
    base_url = f"https://api.openalex.org/works?filter=author.id:{author_id}&per-page=200"
    works = []
    cursor = "*"
    count = 0
    while cursor and count < max_results:
        url = f"{base_url}&cursor={cursor}"
        r = requests.get(url)
        if r.status_code != 200:
            logging.warning(f"Failed to fetch works (status: {r.status_code})")
            break
        data = r.json()
        works.extend(data.get("results", []))
        cursor = data.get("meta", {}).get("next_cursor", None)
        count += len(data.get("results", []))
        time.sleep(1)
    return works

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

# ---------- MAIN PROCESSING ----------
def process_author(search_name):
    logging.info(f"🔍 Starting collection for: {search_name}")
    author_id, author_name = search_openalex_author_id(search_name)
    if not author_id:
        logging.warning(f"No OpenAlex author found for: {search_name}")
        print(f"❌ No author found for: {search_name}")
        return

    works = get_openalex_author_works(author_id)
    unique_works = {w['doi']: w for w in works if w.get("doi")}.values()
    logging.info(f"Found {len(unique_works)} unique works with DOIs for {author_name}")

    results = []
    for work in unique_works:
        doi = work.get("doi")
        title = work.get("title", "Untitled")
        year = work.get("publication_year", "N/A")
        citations = work.get("cited_by_count", 0)
        authors = "; ".join([auth['author']['display_name'] for auth in work.get("authorships", [])])
        venue = work.get("host_venue", {}).get("display_name", "N/A")
        fields = "; ".join([c["display_name"] for c in work.get("concepts", [])])
        pub_type = "Preprint" if work.get("type") == "posted-content" else "Published"

        altmetric = get_altmetric_summary(doi)
        altmetric_id = altmetric.get("altmetric_id") if altmetric else None
        sources = get_altmetric_sources(altmetric_id) if altmetric_id else []

        oa_flag, oa_status = get_open_access_status(doi)

        results.append({
            "Author": author_name,
            "Paper Title": title,
            "Year": year,
            "Publication Type": pub_type,
            "Citations": citations,
            "DOI": doi,
            "Authors": authors,
            "Journal": venue,
            "Fields": fields,
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
        safe_name = search_name.lower().replace(' ', '_')

        os.makedirs("csv", exist_ok=True)
        os.makedirs("json", exist_ok=True)

        csv_file = f"csv/{safe_name}_impact_metrics.csv"
        json_file = f"json/{safe_name}_impact_metrics.json"

        df.to_csv(csv_file, index=False)
        df.to_json(json_file, orient="records", indent=2)


        logging.info(f"✅ Saved for {search_name}: {csv_file}, {json_file}")
        print(f"✅ Finished for {search_name} — {csv_file}")
    else:
        logging.warning(f"No valid papers found for {search_name}")
        print(f"⚠️ No valid papers found for {search_name}")

# ---------- AUTHOR LOOP ----------
author_list = [
    "Jude Kong",
    "Nicola L. Bragazzi"
]

for name in author_list:
    process_author(name)

print("🎉 All authors processed. Check your output and log files.")
