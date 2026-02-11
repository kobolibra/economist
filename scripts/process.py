import os
import zipfile
import shutil
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

# --------------------------------------------------
# 配置与常量
# --------------------------------------------------

INPUT_EPUB = "input/economist.epub"

ALLOWED_SECTIONS = {
    "leaders", 
    "by invitation", 
    "briefing", 
    "china", 
    "international", 
    "business", 
    "finance & economics", 
    "science & technology", 
    "culture", 
    "special reports",
    "technology quarterly",
    "essay",
    "the economist reads"
}

def main():
    shutil.rmtree("temp_epub", ignore_errors=True)
    shutil.rmtree("output", ignore_errors=True)
    os.makedirs("temp_epub", exist_ok=True)
    os.makedirs("output/articles", exist_ok=True)
    os.makedirs("output/images", exist_ok=True)
    os.makedirs("output/css", exist_ok=True)

    if not os.path.exists(INPUT_EPUB):
        print(f"Error: {INPUT_EPUB} not found.")
        return

    unzip_epub()
    copy_images()
    css_filename = copy_css()
    ordered_files = get_reading_order("temp_epub")
    edition_date = extract_edition_date("temp_epub", ordered_files)

    articles = []
    current_section = "Unknown" 

    for html_file in ordered_files:
        full_path = os.path.join("temp_epub", html_file)
        if not os.path.exists(full_path): continue
        new_articles, current_section = parse_html_file(full_path, current_section, css_filename)
        for art in new_articles:
            sec_norm = art['section'].strip().lower()
            if sec_norm in ALLOWED_SECTIONS:
                articles.append(art)

    generate_index(articles, edition_date)
    print(f"Done. Generated {len(articles)} articles.")

# --------------------------------------------------
# 辅助函数 (保持不变)
# --------------------------------------------------

def unzip_epub():
    with zipfile.ZipFile(INPUT_EPUB, "r") as z:
        z.extractall("temp_epub")

def copy_images():
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp")):
                shutil.copy2(os.path.join(root, f), os.path.join("output/images", f))

def copy_css():
    css_name = None
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.lower().endswith(".css"):
                shutil.copy2(os.path.join(root, f), os.path.join("output/css", f))
                css_name = f
    return css_name

def get_reading_order(base_dir):
    opf_path = None
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.endswith(".opf"):
                opf_path = os.path.join(root, f)
                break
        if opf_path: break
    if not opf_path: return []
    try:
        tree = ET.parse(opf_path)
        root = tree.getroot()
        ns = {'opf': 'http://www.idpf.org/2007/opf'}
        manifest = {item.get("id"): item.get("href") for item in root.findall(".//opf:item", ns)}
        if not manifest: manifest = {item.get("id"): item.get("href") for item in root.findall(".//item")}
        spine_ids = [itemref.get("idref") for itemref in root.findall(".//opf:itemref", ns)]
        if not spine_ids: spine_ids = [itemref.get("idref") for itemref in root.findall(".//itemref")]
        opf_dir = os.path.dirname(opf_path)
        return [os.path.relpath(os.path.join(opf_dir, manifest[sid]), base_dir) for sid in spine_ids if sid in manifest]
    except: return []

def extract_edition_date(base_dir, ordered_files):
    date_pattern = re.compile(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?\s+20\d{2}', re.IGNORECASE)
    for fname in ordered_files[:5]:
        path = os.path.join(base_dir, fname)
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                match = date_pattern.search(BeautifulSoup(f.read(), "html.parser").get_text(" ", strip=True))
                if match: return match.group(0)
        except: continue
    return ""

# --------------------------------------------------
# 针对性修改：解析逻辑
# --------------------------------------------------

def parse_html_file(filepath, current_section, css_filename):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    
    body = soup.find("body")
    if not body: return [], current_section

    articles = []
    # 按照源文件结构扫描
    tags = body.find_all(["h1", "h2"])
    
    for tag in tags:
        if tag.name == "h2":
            temp_section = tag.get_text(strip=True)
            if temp_section: current_section = temp_section
            continue

        if tag.name == "h1":
            title = tag.get_text(strip=True)
            
            # --- 精准寻找 Rubric ---
            # 逻辑：在 h1 附近寻找 class 包含 'rubric' 或 'kicker' 的 p 标签
            rubric_text = ""
            # 1. 检查紧邻的前一个标签
            prev_tag = tag.find_previous_sibling()
            if prev_tag and ('rubric' in str(prev_tag.get('class', [])) or 'kicker' in str(prev_tag.get('class', []))):
                rubric_text = prev_tag.get_text(strip=True)
            
            # 2. 如果没找到，检查 h1 内部是否包裹了 rubric (某些版本会把 rubric 放在 h1 前面)
            if not rubric_text:
                candidate = tag.find_previous(["p", "div"])
                if candidate and 'rubric' in str(candidate.get('class', [])):
                    rubric_text = candidate.get_text(strip=True)

            # 构造页眉：Section | Rubric
            header_display = f"{current_section}"
            if rubric_text:
                header_display += f" | {rubric_text}"
            
            fly_title_html = f'<div class="fly-title">{header_display}</div>'
            
            # 收集内容
            content_nodes = [tag]
            for sib in tag.next_siblings:
                if getattr(sib, "name", None) in ["h1", "h2"]: break
                content_nodes.append(sib)

            article_html = fly_title_html + "".join(str(x) for x in content_nodes)
            article_html = re.sub(r'src=["\']([^"\']*?/)?([^/"\']+\.(jpg|jpeg|png|gif|svg|webp))["\']', r'src="../images/\2"', article_html, flags=re.IGNORECASE)

            if len(article_html) < 200: continue

            slug = re.sub(r"[^\w\s-]", "", title).replace(" ", "-").lower()[:80]
            if os.path.exists(f"output/articles/{slug}.html"): slug = f"{slug}-{len(articles)}"
            
            path = f"articles/{slug}.html"
            write_article(path, article_html, title, css_filename)
            articles.append({"section": current_section, "title": title, "path": path})

    return articles, current_section

def write_article(path, html_content, title, css_filename):
    css_link = f'<link rel="stylesheet" href="../css/{css_filename}" type="text/css"/>' if css_filename else ""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
{css_link}
<style>
    body {{ max-width: 850px; margin: 0 auto; padding: 20px; font-family: Georgia, serif; background-color: #fdfdfd; color: #111; line-height: 1.6; }}
    img {{ max-width: 100%; height: auto; display: block; margin: 20px auto; }}
    /* 页眉样式：对应 Section | Rubric */
    .fly-title {{ 
        text-transform: uppercase; 
        font-size: 0.85em; 
        color: #e3120b; 
        margin-bottom: 12px;
        border-bottom: 1px solid #e0e0e0;
        padding-bottom: 6px;
        font-family: "ITC Franklin Gothic", "Helvetica Neue", Arial, sans-serif;
        font-weight: 700;
        letter-spacing: 0.08em;
    }}
    h1 {{ font-size: 2.2em; line-height: 1.2; margin-top: 10px; }}
</style>
</head>
<body class="article">
<div class="main-content">{html_content}</div>
</body>
</html>"""
    with open(f"output/{path}", "w", encoding="utf-8") as f: f.write(html)

def generate_index(articles, edition_date):
    date_html = f'<span class="edition-date">{edition_date}</span>' if edition_date else ""
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Economist {edition_date}</title>
<style>
    body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f8f9fa; }}
    h1 {{ text-align: center; color: #e3120b; font-family: Georgia, serif; margin-bottom: 40px; }}
    .edition-date {{ display: block; font-size: 0.6em; color: #555; margin-top: 5px; font-weight: normal; }}
    h2.section-header {{ background-color: #2c2c2c; color: #fff; padding: 10px 15px; margin-top: 40px; font-size: 1.2em; text-transform: uppercase; border-radius: 4px; }}
    div.article-link {{ margin: 10px 0; padding: 15px; background: white; border-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); border-left: 4px solid transparent; }}
    div.article-link:hover {{ border-left: 4px solid #e3120b; transform: translateY(-1px); box-shadow: 0 3px 6px rgba(0,0,0,0.1); }}
    a {{ text-decoration: none; color: #1a1a1a; font-weight: bold; display: block; }}
</style>
</head>
<body>
<h1>The Economist {date_html}</h1>
"""
    current_section = None
    for a in articles:
        if a["section"] != current_section:
            current_section = a["section"]
            html += f'<h2 class="section-header">{current_section}</h2>'
        html += f'<div class="article-link"><a href="{a["path"]}">{a["title"]}</a></div>'
    html += "</body></html>"
    with open("output/index.html", "w", encoding="utf-8") as f: f.write(html)

if __name__ == "__main__":
    main()
