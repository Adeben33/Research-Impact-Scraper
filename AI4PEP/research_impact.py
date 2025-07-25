import pandas as pd
import requests
import time
import logging
import os
import re
import json
import random
from scholarly import scholarly


# ---------- CONFIG ----------
UNPAYWALL_EMAIL = "adeniyiebenezer33@gmail.com"
DEBUG_MODE = True
REFRESH_CACHE = True

OUTPUT_DIR = "."
os.makedirs(OUTPUT_DIR, exist_ok=True)


LOG_FILE = os.path.join(OUTPUT_DIR, 'research_impact_log.txt')
# ---------- LOGGING ----------
logging.basicConfig(
    filename='LOG_FILE',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


# NEW – filter switch
FILTER_BY_JUDE       = True
JUDE_NAME_VARIANTS   = ["jude dzevela kong", "jude kong"]

def safe_get(url, params=None, headers=None, timeout=20, max_retries=3, backoff_factor=1.5):
    for i in range(max_retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200:
                time.sleep(random.uniform(1.5, 3.0))  # polite delay
                return r
            elif r.status_code in [429, 503]:
                wait = backoff_factor ** (i + 1)
                logging.warning(f"Rate limited (status {r.status_code}). Retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                logging.warning(f"Unexpected status {r.status_code} for URL: {url}")
                break
        except requests.RequestException as e:
            logging.warning(f"Request error on attempt {i + 1} for {url}: {e}")
            time.sleep(backoff_factor ** (i + 1))
    return None



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
        r = requests.get(url, timeout=20)
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
        r = requests.get(url, timeout=20)
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
        r = requests.get(url, params=params, timeout=20)
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
            print(f"🔗 Altmetric URL: {url} — Status: {r.status_code}")
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
            print(f"🔗 Altmetric PMID URL: {url} — Status: {r.status_code}")
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


# ---------- DOAJ CHECK ----------
def is_journal_in_doaj(journal_title):
    try:
        url = f"https://doaj.org/api/v2/search/journals/{journal_title}"
        r = requests.get(url)
        if r.status_code == 200 and 'total' in r.json():
            return True, "doaj"
    except:
        pass
    return None, None


# ---------- CORE CHECK ----------
def is_in_core_repository(doi):
    try:
        if not doi:
            return None, None
        core_indexed_prefixes = ["10.5281", "10.31235", "10.1101", "10.6084"]
        if any(doi.startswith(prefix) for prefix in core_indexed_prefixes):
            return True, "mocked_core"
    except Exception as e:
        logging.warning(f"CORE check failed for DOI {doi}: {e}")
    return None, None


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


# ---------- HELPERS ----------
def tag_keywords(text, keyword_list):
    return any(k in text.lower() for k in keyword_list)


def has_media_mentions(altmetric):
    if not altmetric:
        return False
    counts = altmetric.get("counts", {})
    return any(counts.get(k, 0) > 0 for k in ['News', 'Blogs', 'Policy Docs', 'Facebook', 'Wikipedia'])


def is_preprint(venue, doi):
    if doi:
        return False
    preprint_sources = ["arxiv", "biorxiv", "medrxiv", "ssrn", "osf", "researchsquare", "preprints"]
    return any(src in venue.lower() for src in preprint_sources) if venue else False


# ---------- GOOGLE SCHOLAR ----------
def get_author_by_user_id(user_id):
    try:
        author = scholarly.search_author_id(user_id)
        filled = scholarly.fill(author)
        return filled, filled['name']
    except Exception as e:
        logging.error(f"Error fetching scholar profile for user ID {user_id}: {e}")
    return None, None


# ---------- DOAJ CHECK ----------
def is_journal_in_doaj(journal_title):
    try:
        url = f"https://doaj.org/api/v2/search/journals/{journal_title}"
        r = requests.get(url)
        if r.status_code == 200 and 'total' in r.json():
            return True, "doaj"
    except:
        pass
    return None, None


# ---------- CORE CHECK ----------
def is_in_core_repository(doi):
    try:
        if not doi:
            return None, None
        core_indexed_prefixes = ["10.5281", "10.31235", "10.1101", "10.6084"]
        if any(doi.startswith(prefix) for prefix in core_indexed_prefixes):
            return True, "mocked_core"
    except Exception as e:
        logging.warning(f"CORE check failed for DOI {doi}: {e}")
    return None, None


# ---------- UNPAYWALL CHECK ----------
def get_open_access_status_unpaywall(doi):
    url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
    try:
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            return data.get("is_oa", False), data.get("oa_status", "unknown")
    except Exception as e:
        logging.warning(f"Unpaywall error for DOI {doi}: {e}")
    return None, None


# ---------- CROSSREF LICENSE CHECK ----------
def get_open_access_status_crossref_license(doi):
    try:
        url = f"https://api.crossref.org/works/{doi}"
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            licenses = r.json()['message'].get("license", [])
            if licenses:
                return True, licenses[0].get("URL", "")
    except Exception as e:
        logging.warning(f"Crossref license check failed for {doi}: {e}")
    return None, None


# ---------- PREPRINT CHECK ----------
def is_preprint_venue(venue, doi):
    if doi:
        return False, None
    preprint_sources = ["arxiv", "biorxiv", "medrxiv", "ssrn", "osf", "researchsquare", "preprints"]
    if venue:
        for src in preprint_sources:
            if src in venue.lower():
                return True, src
    return False, None


# ---------- OA BUTTON CHECK ----------
def get_open_access_from_oa_button(doi):
    try:
        url = f"https://api.openaccessbutton.org/find?id=https://doi.org/{doi}"
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            oa_link = data.get("data", {}).get("url")
            if oa_link:
                return True, oa_link
    except Exception as e:
        logging.warning(f"OA Button error for DOI {doi}: {e}")
    return None, None


# ---------- COMBINED OA CHECK ----------
def get_combined_open_access_status(doi, venue):
    oa, source = is_journal_in_doaj(venue)
    if oa is not None:
        return oa, f"doaj"

    oa, source = is_in_core_repository(doi)
    if oa is not None:
        return oa, f"core:{source}"

    oa, source = get_open_access_status_unpaywall(doi)
    if oa is not None:
        return oa, f"unpaywall:{source}"

    oa, source = get_open_access_status_crossref_license(doi)
    if oa is not None:
        return oa, f"crossref_license:{source}"

    oa, source = is_preprint_venue(venue, doi)
    if oa:
        return oa, f"preprint:{source}"

    oa, source = get_open_access_from_oa_button(doi)
    if oa is not None:
        return oa, f"oa_button:{source}"

    return False, "unknown"


# ---------- SAFE FILL ----------
def safe_fill(pub, retries=3, delay=2):
    for attempt in range(retries):
        try:
            return scholarly.fill(pub)
        except Exception as e:
            logging.warning(f"Retry {attempt + 1} for fill failed: {e}")
            time.sleep(delay)
    return None


def get_scholar_publications(filled_author, max_results=3000):
    author_dir = os.path.join(OUTPUT_DIR, filled_author['name'].lower().replace(' ', '_'))
    os.makedirs(author_dir, exist_ok=True)
    cache_file = f"{author_dir}/cached_publications.json"

    if not REFRESH_CACHE and os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            return json.load(f)

    publications = []
    for pub in filled_author.get('publications', [])[:max_results]:
        try:
            detailed = safe_fill(pub)
            if not detailed:
                continue
            title = detailed['bib'].get("title", "Untitled")
            year = detailed['bib'].get("pub_year", "N/A")
            authors = detailed['bib'].get("author", "")
            venue = detailed['bib'].get("journal") or detailed['bib'].get("venue") or detailed['bib'].get("pub") or "N/A"
            citations = detailed.get("num_citations", 0)
            doi = detailed.get("pub_url", "")

            # Filter by publication year >= 2023
            try:
                if year != "N/A" and int(year) < 2023:
                    continue
            except:
                continue  # skip if year cannot be parsed

            publications.append({
                "title": title,
                "year": year,
                "authors": authors,
                "venue": venue,
                "citations": citations,
                "doi": doi
            })
            time.sleep(10)
        except Exception as e:
            logging.warning(f"Failed to fill publication: {e}")

    try:
        with open(cache_file, "w") as f:
            json.dump(publications, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to write cache file for {author_dir}: {e}")

    return publications


def classify_publication_type(doi, venue, oa_flag):
    if is_preprint(venue, doi):
        return "Preprint"
    elif doi and oa_flag:
        return "Open Access"
    elif doi:
        return "Published"
    else:
        return "Unknown"


def fallback_oa_from_doi_url(doi):
    open_domains = ["plos.org", "bmc.org", "frontiersin.org", "mdpi.com", "peerj.com"]
    for domain in open_domains:
        if domain in doi:
            return True
    return False


def refine_open_access_label(is_oa, oa_status):
    if not is_oa or oa_status == "closed":
        return "Closed"
    elif oa_status == "gold":
        return "Gold OA"
    elif oa_status == "green":
        return "Green OA"
    elif oa_status == "hybrid":
        return "Hybrid OA"
    elif oa_status == "bronze":
        return "Bronze OA"
    else:
        return "Unknown OA"


# ---------- PROCESS ----------
def process_author(author_name, profile, works):
    # safe_name = author_name.lower().replace(' ', '_')
    safe_name = os.path.join(OUTPUT_DIR, author_name.lower().replace(' ', '_'))
    os.makedirs(safe_name, exist_ok=True)
    results = []
    altmetric_404_titles = []

    # Save author-level metrics
    profile_metrics = {
        "Author": author_name,
        "Citations_All": profile.get("citedby", 0),
        "Citations_Since2020": profile.get("citedby5y", 0),
        "h_index_All": profile.get("hindex", 0),
        "h_index_Since2020": profile.get("hindex5y", 0),
        "i10_index_All": profile.get("i10index", 0),
        "i10_index_Since2020": profile.get("i10index5y", 0)
    }
    pd.DataFrame([profile_metrics]).to_csv(f"{safe_name}/metrics.csv", index=False)
    pd.DataFrame([profile_metrics]).to_json(f"{safe_name}/metrics.csv", orient="records", indent=2)

    for work in works:
        title = work.get("title", "Untitled")
        year = work.get("year", "N/A")
        authors = work.get("authors", "")

        if FILTER_BY_JUDE and not any(n in authors.lower() for n in JUDE_NAME_VARIANTS):
            continue
        venue = work.get("venue", "N/A")
        citations = work.get("citations", 0)
        raw_doi = work.get("doi", "")
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

        print(f"📄 Processing: {title} ({doi if doi else 'No DOI'})")
        altmetric = get_altmetric_summary(doi, pmid, title=title, altmetric_404_log=altmetric_404_titles)
        media_flag = has_media_mentions(altmetric)
        counts = altmetric.get("counts", {}) if altmetric else {}
        oa_flag, oa_status_raw = get_combined_open_access_status(doi, venue)
        oa_type = refine_open_access_label(oa_flag, oa_status_raw)

        # paper_link = f"https://doi.org/{doi}" if doi else raw_doi if raw_doi.startswith("http") else "N/A"

        is_preprint_flag = is_preprint(venue, doi)

        paper_link = (
            f"https://doi.org/{doi}" if doi else
            raw_doi if is_preprint_flag and raw_doi.startswith("http") else
            "N/A"
        )

        results.append({
            "Author": author_name,
            "Paper Title": title,
            "Year": year,
            "Citations": citations,
            "DOI": f"https://doi.org/{doi}" if doi else "N/A",
            "PMID": pmid,
            "Authors": authors,
            "Journal": venue,
            "Altmetric Score": altmetric.get("score") if altmetric else 0,
            "Twitter Mentions": counts.get("Twitter", 0),
            "Reddit Mentions": counts.get("Reddit", 0),
            "News Mentions": counts.get("News", 0),
            "Blog Mentions": counts.get("Blogs", 0),
            "Facebook Mentions": counts.get("Facebook", 0),
            "Wikipedia Mentions": counts.get("Wikipedia", 0),
            "Policy Mentions": counts.get("Policy Docs", 0),
            "Media Mentioned": media_flag,
            "Open Access": oa_flag,
            "OA Status": oa_status_raw,
            "Preprint": is_preprint(venue, doi),
            "Publication Type": classify_publication_type(doi, venue, oa_flag),
            "Public Health Impact": tag_keywords(title, public_health_keywords),
            "Capacity Building": tag_keywords(title, capacity_building_keywords),
            "Paper Link": paper_link
        })
        time.sleep(10)

    if results:
        df = pd.DataFrame(results)
        df.to_csv(f"{safe_name}/impact_metrics.csv", index=False)
        df.to_json(f"{safe_name}/impact_metrics.json", orient="records", indent=2)
        print(f"✅ Finished for {author_name} — {len(results)} papers saved.")

    if altmetric_404_titles:
        pd.DataFrame(altmetric_404_titles, columns=["Title"]).to_csv(
            f"{safe_name}/altmetric_404.csv", index=False
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

# ----------AI4PEP AUTHOR DICTIONARY ----------
author_dict = {
    #"Jude Dzevela Kong": "dPAVmL0AAAAJ",
    "Denis Nkweteyim":"4UR2BucAAAAJ",
    "Gelan Ayana":"bNK6lMoAAAAJ",
    "Kingsley Badu": "de6nT0EAAAAJ",
    "Evelyn Kissi": "ZsuY1NsAAAAJ",
    "Rachel Gorman": "6VcJPOEAAAAJ",
    "Sylvain Landry Faye": "B6hMjn4AAAAJ",
    # "Bruce Mellado": "BTJnR0UAAAAJ" #not done
    "Adesina Simon Sodiya": "iNnkbzgAAAAJ",
    "Riris Andono Ahmad": "H3T6XqcAAAAJ",
     "Serge Demidenko": "0DcFUWkAAAAJ",
     "Romulo de Castro": "Hi5-8lwAAAAJ",
     "Tseren-Onolt Ishdorj": "0WHrk08AAAAJ",
     "Andre de Carvalho": "Jx_5GrgAAAAJ",
     "Manuel Colome": "aKZ8i6IAAAAJ",
     "Cesar Ugarte-Gil": "oMSZ_EgAAAAJ",
     "Simon Anderson": "eVPe_kAAAAAJ",
     "Radwan Qasrawi": "eVPe_kAAAAAJ",
     "Elie Sokhn": "xPIHn-MAAAAJ",
     "Yahya Tayalati": "MuR6AzYAAAAJ",
     "Sadri Znaidi": "qNuluioAAAAJ",
     "Franklin Asiedu-Bekoe": "nLQtW2kAAAAJ",
     "Michael Owusu": "IPTvRYcAAAAJ",
     "Christo El Morr": "X58b2IAAAAJ",
     "Collins Adu": "0ujYGxoAAAAJ",
     "Rose-Mary Owusuaa Mensah Gyening": "pLbPQXkAAAAJ",
     "Jerry Kponyoh": "feQo2zYAAAAJ",
     "Peter Haddawy": "lovm5cAAAAAJ",
     "Rudith King": "eZs2YKwAAAAJ",
     "Anuwat Wiratsudakul": "wfovEncAAAAJ",
     "Gideon Anapey": "12TF5uEAAAAJ",
     "Dolvara Gunatilaka": "b8LUlLkAAAAJ",
     "Augustina Sylverken": "i4W1CtsAAAAJ",
     "Saranath Lawpoolsri": "ycuPRikAAAAJ",
     "Edmund Yamba": "Br4DbcIAAAAJ",
     "Patchara Sriwichai": "BYW6VxcAAAAJ",
     "Ibrahima Dia": "SjstYn0AAAAJ",
     "Massamba Diouf": "9jQ4KJIAAAAJ",
     "Halima Diallo": "Qd3EZREAAAAJ",
     "Vincent Duclos": "sqXi04wAAAAJ",
     "Pallab Basu": "A8upqZoAAAAJ",
     "Shamayeta Bhattacharya": "JYKiu1YAAAAJ",
     "Vongani Chabalala": "NjifuRwAAAAJ",
     "Mpho Gololo": "uYVSpLMAAAAJ",
     "Mary Kawonga": "hOwZrkAAAAAJ",
     "Benjamin Lieberman": "Ll1tz1UAAAAJ",
     "Edward Nkadimeng": "idJhYpUAAAAJ",
     "Busisiwe Nkala-Dlamini": "oATqSg4AAAAJ",
     "Chuene Mosomane": "rme82R4AAAAJ",
     "Ketema Lemma": "TTaX1mcAAAAJ",
     "Victor Ngu Ngwa": "wjYy0nsAAAAJ",
     "Zahra Movahedi Nia": "g9EbkyoAAAAJ",
     "Hundessa Daba": "oXqyAqMAAAAJ",
     "Bontu Habtamu": "6zRhejEAAAAJ",
     "Gashaw Demlew": "2Vtu-KsAAAAJ",
     "Elbetel Taye": "fo-Q3Y0AAAAJ",
     "Mikias Alayu": "xTS5iYIAAAAJ"
}

# ---------- EXECUTION ----------
for author_name, user_id in author_dict.items():
    print(f"🔍 Retrieving data for {author_name}...")
    profile, _ = get_author_by_user_id(user_id)
    if profile:
        works = get_scholar_publications(profile)
        process_author(author_name, profile, works)
    else:
        print(f"❌ Could not retrieve profile for {author_name}")

print("🎉 All authors processed. Check your output folders.")
