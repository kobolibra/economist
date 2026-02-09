import os
import zipfile
import shutil
import re
from collections import OrderedDict

INPUT_EPUB = "input/economist.epub"

# 定义需要保留的 section，按此顺序展示
TARGET_SECTIONS = [
    "Leaders",
    "By Invitation",
    "Briefing",
    "China",
    "International",
    "Business",
    "Finance & economics",
    "Science & technology",
    "Culture"
]

# Section 名称标准化映射
SECTION_ALIASES = {
    "leader": "Leaders",
    "leaders": "Leaders",
    "by invitation": "By Invitation",
    "briefing": "Briefing",
    "china": "China",
    "international": "International",
    "business": "Business",
    "finance & economics": "Finance & economics",
    "finance and economics": "Finance & economics",
    "science & technology": "Science & technology",
    "science and technology": "Science & technology",
    "culture": "Culture"
}


def normalize_section_name(name):
    """标准化 section 名称"""
    key = name.lower().strip()
    return SECTION_ALIASES.get(key, name)


def main():
    shutil.rmtree("temp_epub", ignore_errors=True)
    shutil.rmtree("output", ignore_errors=True)

    os.makedirs("temp_epub", exist_ok=True)
    os.makedirs("output/articles", exist_ok=True)
    os.makedirs("output/images", exist_ok=True)

    unzip_epub()
    copy_images()

    # 从 nav.xhtml 解析 section -> 文章列表 的映射
    sections = parse_nav_xhtml()
    
    # 过滤并排序 sections
    filtered_sections = OrderedDict()
    for target in TARGET_SECTIONS:
        normalized_target = normalize_section_name(target)
        for section_name, articles in sections.items():
            if normalize_section_name(section_name) == normalized_target:
                filtered_sections[normalized_target] = articles
                break

    # 处理每个文章并生成页面
    for section_name, articles in filtered_sections.items():
        for article in articles:
            process_article(article, section_name)

    generate_index(filtered_sections)
    
    total_articles = sum(len(articles) for articles in filtered_sections.values())
    print(f"Done. Sections: {len(filtered_sections)}, Articles: {total_articles}")


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


def parse_nav_xhtml():
    """从 nav.xhtml 解析 section 和文章结构"""
    nav_path = "temp_epub/EPUB/nav.xhtml"
    if not os.path.exists(nav_path):
        # 尝试其他可能的路径
        nav_path = "temp_epub/nav.xhtml"
    
    with open(nav_path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    # 使用简单的正则表达式解析，避免依赖 BeautifulSoup
    sections = OrderedDict()
    current_section = None
    
    # 匹配 <span>Section Name</span> 或 <li><span>Section</span><ol>...</ol></li>
    section_pattern = re.compile(r'<li[^>]*>\s*<span>([^<]+)</span>\s*<ol>(.*?)</ol>', re.DOTALL)
    article_pattern = re.compile(r'<a href="([^"]+)">([^<]+)</a>')
    
    for section_match in section_pattern.finditer(html):
        section_name = section_match.group(1).strip()
        section_content = section_match.group(2)
        
        articles = []
        for article_match in article_pattern.finditer(section_content):
            file_path = article_match.group(1).strip()
            title = article_match.group(2).strip()
            articles.append({
                "title": title,
                "file": file_path
            })
        
        if articles:
            sections[section_name] = articles
    
    return sections


def process_article(article, section_name):
    """处理单个文章文件"""
    file_path = os.path.join("temp_epub/EPUB", article["file"])
    if not os.path.exists(file_path):
        print(f"Warning: File not found: {file_path}")
        return
    
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()
    
    # 提取文章内容（body 内部的所有内容）
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
    if not body_match:
        return
    
    body_content = body_match.group(1)
    
    # 清理内容：移除脚本和样式
    body_content = re.sub(r'<script[^>]*>.*?</script>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
    body_content = re.sub(r'<style[^>]*>.*?</style>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
    
    # 修复图片路径
    body_content = re.sub(
        r'src=["\']([^"\']*?/)?([^/"\']+\.(jpg|jpeg|png|gif|svg|webp))["\']',
        r'src="../images/\2"',
        body_content,
        flags=re.IGNORECASE
    )
    
    # 生成 slug
    slug = re.sub(r"[^\w\s-]", "", article["title"]).replace(" ", "-").lower()[:80]
    article["path"] = f"articles/{slug}.html"
    article["slug"] = slug
    
    write_article(article["path"], article["title"], body_content, section_name)


def write_article(path, title, html_content, section):
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | The Economist</title>
    <style>
        body {{
            font-family: Georgia, "Times New Roman", serif;
            font-size: 18px;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
        }}
        .section-label {{
            font-family: Arial, sans-serif;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
            color: #E3120B;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }}
        h1 {{
            font-size: 32px;
            font-weight: normal;
            color: #000;
            margin-bottom: 20px;
            line-height: 1.2;
        }}
        h2, h3, h4 {{
            font-family: Arial, sans-serif;
            margin-top: 30px;
            margin-bottom: 15px;
        }}
        p {{
            margin-bottom: 1em;
            text-align: justify;
        }}
        img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 20px auto;
        }}
        .back-link {{
            display: inline-block;
            margin-top: 40px;
            font-family: Arial, sans-serif;
            font-size: 14px;
            color: #666;
            text-decoration: none;
        }}
        .back-link:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="section-label">{section}</div>
    {html_content}
    <a href="../index.html" class="back-link">← Back to index</a>
</body>
</html>
"""

    with open(f"output/{path}", "w", encoding="utf-8") as f:
        f.write(html)


def generate_index(sections):
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>The Economist - Weekly Edition</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 40px 20px;
            background-color: #fff;
            color: #333;
        }}
        header {{
            background-color: #E3120B;
            color: white;
            padding: 30px;
            text-align: center;
            margin-bottom: 40px;
        }}
        h1 {{
            margin: 0;
            font-family: Georgia, serif;
            font-size: 42px;
            font-weight: normal;
        }}
        .section {{
            margin-bottom: 40px;
        }}
        .section-header {{
            border-bottom: 3px solid #E3120B;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .section-title {{
            font-family: Georgia, serif;
            font-size: 24px;
            font-weight: bold;
            text-transform: uppercase;
            color: #E3120B;
            margin: 0;
        }}
        .article-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .article-item {{
            padding: 12px 0;
            border-bottom: 1px solid #eee;
        }}
        .article-link {{
            text-decoration: none;
            color: #333;
            font-family: Georgia, serif;
            font-size: 18px;
        }}
        .article-link:hover {{
            color: #E3120B;
        }}
    </style>
</head>
<body>
    <header>
        <h1>The Economist</h1>
        <p>Weekly Edition</p>
    </header>
"""

    for section_name, articles in sections.items():
        if not articles:
            continue
            
        html += f'''
    <section class="section">
        <div class="section-header">
            <h2 class="section-title">{section_name}</h2>
        </div>
        <ul class="article-list">
'''
        
        for article in articles:
            if "path" in article:
                html += f'''            <li class="article-item">
                <a href="{article["path"]}" class="article-link">{article["title"]}</a>
            </li>
'''
        
        html += '''        </ul>
    </section>
'''

    html += """</body>
</html>
"""

    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
