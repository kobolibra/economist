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
    "culture"
}

def main():
    # 1. 环境清理与初始化
    shutil.rmtree("temp_epub", ignore_errors=True)
    shutil.rmtree("output", ignore_errors=True)

    os.makedirs("temp_epub", exist_ok=True)
    os.makedirs("output/articles", exist_ok=True)
    os.makedirs("output/images", exist_ok=True)
    os.makedirs("output/css", exist_ok=True)

    if not os.path.exists(INPUT_EPUB):
        print(f"Error: {INPUT_EPUB} not found.")
        return

    # 2. 解压 EPUB
    print("Unzipping epub...")
    unzip_epub()
    
    # 3. 提取资源
    copy_images()
    css_filename = copy_css()

    # 4. 获取阅读顺序
    print("Parsing reading order...")
    ordered_files = get_reading_order("temp_epub")
    
    # --- 新增功能：提取日期 ---
    print("Extracting edition date...")
    edition_date = extract_edition_date("temp_epub", ordered_files)
    print(f"Edition Date found: {edition_date}")
    # -----------------------

    articles = []
    current_section = "Unknown" 

    # 5. 解析 HTML
    print(f"Processing {len(ordered_files)} files...")
    for html_file in ordered_files:
        full_path = os.path.join("temp_epub", html_file)
        if not os.path.exists(full_path):
            continue
            
        new_articles, current_section = parse_html_file(full_path, current_section, css_filename)
        
        for art in new_articles:
            sec_norm = art['section'].strip().lower()
            if sec_norm in ALLOWED_SECTIONS:
                articles.append(art)

    # 6. 生成索引 (传入日期)
    generate_index(articles, edition_date)

    print(f"Done. Generated {len(articles)} articles.")


# --------------------------------------------------
# 核心逻辑
# --------------------------------------------------

def unzip_epub():
    with zipfile.ZipFile(INPUT_EPUB, "r") as z:
        z.extractall("temp_epub")

def copy_images():
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp")):
                src = os.path.join(root, f)
                dst = os.path.join("output/images", f)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)

def copy_css():
    css_name = None
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.lower().endswith(".css"):
                src = os.path.join(root, f)
                dst = os.path.join("output/css", f)
                shutil.copy2(src, dst)
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
        namespaces = {'opf': 'http://www.idpf.org/2007/opf'}
        
        manifest = {}
        for item in root.findall(".//opf:item", namespaces):
            manifest[item.get("id")] = item.get("href")
        if not manifest:
            for item in root.findall(".//item"):
                manifest[item.get("id")] = item.get("href")

        spine_ids = []
        for itemref in root.findall(".//opf:itemref", namespaces):
            spine_ids.append(itemref.get("idref"))
        if not spine_ids:
            for itemref in root.findall(".//itemref"):
                spine_ids.append(itemref.get("idref"))
            
        opf_dir = os.path.dirname(opf_path)
        ordered_files = []
        for spin_id in spine_ids:
            href = manifest.get(spin_id)
            if href:
                full_path = os.path.join(opf_dir, href)
                rel_path = os.path.relpath(full_path, base_dir)
                ordered_files.append(rel_path)
        return ordered_files
    except Exception as e:
        print(f"Error parsing OPF: {e}")
        return []

# --- 新增函数：日期提取 ---
def extract_edition_date(base_dir, ordered_files):
    """
    尝试从前 5 个文件中提取日期（格式如 February 7th 2026）
    """
    # 匹配月份+日+年的正则
    date_pattern = re.compile(
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?\s+20\d{2}',
        re.IGNORECASE
    )
    
    # 只检查前5个文件，通常日期在封面或版权页
    for fname in ordered_files[:5]:
        path = os.path.join(base_dir, fname)
        if not os.path.exists(path): continue
        
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                # 获取纯文本进行匹配
                soup = BeautifulSoup(f.read(), "html.parser")
                text = soup.get_text(" ", strip=True)
                match = date_pattern.search(text)
                if match:
                    return match.group(0) # 返回匹配到的完整日期字符串
        except:
            continue
            
    return "" # 没找到则返回空字符串

# -----------------------

def parse_html_file(filepath, current_section, css_filename):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    if not body:
        return [], current_section

    articles = []
    tags = body.find_all(["h1", "h2"])
    
    for tag in tags:
        if tag.name == "h2":
            temp_section = tag.get_text(strip=True)
            if temp_section:
                current_section = temp_section
            continue

        if tag.name == "h1":
            title = tag.get_text(strip=True)
            if not title: continue

            content_nodes = [tag]
            for sib in tag.next_siblings:
                if getattr(sib, "name", None) in ["h1", "h2"]: break
                content_nodes.append(sib)

            article_html = "".join(str(x) for x in content_nodes)
            article_html = re.sub(
                r'src=["\']([^"\']*?/)?([^/"\']+\.(jpg|jpeg|png|gif|svg|webp))["\']',
                r'src="../images/\2"',
                article_html,
                flags=re.IGNORECASE
            )

            if len(article_html) < 200: continue

            slug = re.sub(r"[^\w\s-]", "", title).replace(" ", "-").lower()[:80]
            if os.path.exists(f"output/articles/{slug}.html"):
                slug = f"{slug}-{len(articles)}"
            
            path = f"articles/{slug}.html"
            write_article(path, article_html, title, css_filename)

            articles.append({
                "section": current_section,
                "title": title,
                "path": path
            })

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
    body {{
        max-width: 900px;
        margin: 0 auto;
        padding: 20px;
        font-family: Georgia, serif;
        background-color: #fdfdfd;
        color: #111;
    }}
    img {{
        max-width: 100%;
        height: auto;
        display: block;
        margin: 20px auto;
    }}
    .fly-title {{ 
        text-transform: uppercase; 
        font-size: 0.8em; 
        color: #e3120b; 
        margin-bottom: 5px;
        display: block;
    }}
</style>
</head>
<body class="article">
<div class="main-content">
{html_content}
</div>
</body>
</html>
"""
    with open(f"output/{path}", "w", encoding="utf-8") as f:
        f.write(html)


# --- 修改功能：生成索引页（日期显示 + 样式优化） ---
def generate_index(articles, edition_date):
    date_html = f'<span class="edition-date">{edition_date}</span>' if edition_date else ""
    
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Economist {edition_date}</title>
<style>
    body {{ 
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
        max-width: 800px; 
        margin: 0 auto; 
        padding: 20px; 
        background-color: #f8f9fa; /* 背景调亮一点 */
    }}
    
    /* 标题样式：包含日期 */
    h1 {{ 
        text-align: center; 
        color: #e3120b; 
        font-family: Georgia, serif; 
        margin-bottom: 40px; 
        line-height: 1.4;
    }}
    .edition-date {{
        display: block;
        font-size: 0.6em;
        color: #555;
        margin-top: 5px;
        font-weight: normal;
        font-family: sans-serif;
    }}

    /* Section 样式优化：增加背景色，使其像一个通栏标题 */
    h2.section-header {{ 
        background-color: #333; /* 深色背景 */
        color: #fff;            /* 白色文字 */
        padding: 8px 15px;      /* 增加内边距 */
        margin-top: 50px; 
        margin-bottom: 15px;
        font-size: 1.3em;       /* 稍微加大 */
        text-transform: uppercase; 
        letter-spacing: 0.05em;
        border-radius: 4px;     /* 圆角 */
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }}
    
    /* 文章链接样式 */
    div.article-link {{ 
        margin: 10px 0; 
        padding: 15px; 
        background: white; 
        border-radius: 4px; 
        box-shadow: 0 1px 2px rgba(0,0,0,0.05); 
        transition: transform 0.1s;
        border-left: 4px solid transparent; /* 预留左侧边框位置 */
    }}
    div.article-link:hover {{ 
        transform: translateY(-2px); 
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); 
        border-left: 4px solid #e3120b; /* 悬停时显示红色左边框 */
    }}
    
    a {{ 
        text-decoration: none; 
        color: #1a1a1a; 
        font-weight: bold; 
        font-size: 1.05em; /* 稍微调整，与 Section 区分 */
        display: block; 
    }}
    a:hover {{ color: #e3120b; }}
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

    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)
# -----------------------

if __name__ == "__main__":
    main()
