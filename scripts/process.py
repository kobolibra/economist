import os
import zipfile
import shutil
import re
from bs4 import BeautifulSoup
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

# Section 名称标准化映射（处理可能的变体）
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


def main():
    shutil.rmtree("temp_epub", ignore_errors=True)
    shutil.rmtree("output", ignore_errors=True)

    os.makedirs("temp_epub", exist_ok=True)
    os.makedirs("output/articles", exist_ok=True)
    os.makedirs("output/images", exist_ok=True)

    unzip_epub()
    copy_images()

    # 使用 OrderedDict 保持顺序: section -> [articles]
    sections = OrderedDict()
    
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.endswith((".html", ".xhtml")):
                path = os.path.join(root, f)
                parse_html_file(path, sections)

    # 过滤并排序 sections
    filtered_sections = OrderedDict()
    for target in TARGET_SECTIONS:
        for section_name, articles in sections.items():
            if normalize_section_name(section_name) == target and articles:
                filtered_sections[target] = articles
                break

    generate_index(filtered_sections)
    print("Done. Sections:", len(filtered_sections))


# --------------------------------------------------

def normalize_section_name(name):
    """标准化 section 名称"""
    key = name.lower().strip()
    return SECTION_ALIASES.get(key, name)


def unzip_epub():
    with zipfile.ZipFile(INPUT_EPUB, "r") as z:
        z.extractall("temp_epub")


# --------------------------------------------------

def copy_images():
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp")):
                src = os.path.join(root, f)
                dst = os.path.join("output/images", f)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)


# --------------------------------------------------

def parse_html_file(filepath, sections):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    if not body:
        return

    current_section = None

    for tag in body.find_all(["h1", "h2", "h3", "h4"]):
        text = tag.get_text(strip=True)
        
        # 识别 section header (h2 或 h3，通常是全大写或特定样式)
        if tag.name in ["h2", "h3"]:
            normalized = normalize_section_name(text)
            if normalized in TARGET_SECTIONS:
                current_section = normalized
                if current_section not in sections:
                    sections[current_section] = []
            continue

        # 识别文章标题 (h1 或 h4，取决于 EPUB 结构)
        if tag.name in ["h1", "h4"]:
            title = text
            if not title or len(title) < 3:
                continue

            # 收集文章内容直到下一个标题
            content_nodes = []
            for sib in tag.next_siblings:
                if getattr(sib, "name", None) in ["h1", "h2", "h3", "h4"]:
                    break
                content_nodes.append(sib)

            if not content_nodes:
                continue

            article_html = "".join(str(x) for x in content_nodes)

            # 修复图片路径
            article_html = re.sub(
                r'src=["\']([^"\']*?/)?([^/"\']+\.(jpg|jpeg|png|gif|svg|webp))["\']',
                r'src="../images/\2"',
                article_html,
                flags=re.IGNORECASE
            )

            # 清理内容
            article_html = clean_article_content(article_html)

            if len(article_html) < 200:
                continue

            # 如果没有识别到 section，跳过
            if not current_section:
                continue

            slug = re.sub(r"[^\w\s-]", "", title).replace(" ", "-").lower()[:80]
            path = f"articles/{slug}.html"

            write_article(path, title, article_html, current_section)

            sections[current_section].append({
                "title": title,
                "path": path
            })


def clean_article_content(html):
    """清理文章内容，移除不必要的标签"""
    soup = BeautifulSoup(html, "html.parser")
    
    # 移除脚本和样式标签
    for tag in soup(["script", "style"]):
        tag.decompose()
    
    # 清理 class 和 id 属性，保留基本结构
    for tag in soup.find_all(True):
        # 保留一些基本的排版相关属性
        keep_attrs = []
        if tag.name == "img":
            keep_attrs = ["src", "alt"]
        elif tag.name in ["a", "p", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6"]:
            keep_attrs = ["class", "id"]
        
        # 移除不需要的属性
        attrs_to_remove = [attr for attr in tag.attrs if attr not in keep_attrs]
        for attr in attrs_to_remove:
            del tag[attr]
    
    return str(soup)


# --------------------------------------------------

def write_article(path, title, html_content, section):
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | The Economist</title>
    <style>
        /* Economist 风格基础排版 */
        :root {{
            --primary-color: #E3120B;
            --text-color: #333;
            --bg-color: #fff;
            --secondary-bg: #f5f5f5;
            --border-color: #ddd;
            --font-serif: "Times New Roman", Times, Georgia, serif;
            --font-sans: "Helvetica Neue", Helvetica, Arial, sans-serif;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: var(--font-serif);
            font-size: 18px;
            line-height: 1.6;
            color: var(--text-color);
            background-color: var(--bg-color);
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
        }}
        
        /* 文章头部 */
        .article-header {{
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid var(--primary-color);
        }}
        
        .section-label {{
            font-family: var(--font-sans);
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
            color: var(--primary-color);
            letter-spacing: 1px;
            margin-bottom: 10px;
        }}
        
        .article-title {{
            font-size: 32px;
            line-height: 1.2;
            font-weight: normal;
            color: #000;
            margin-bottom: 15px;
        }}
        
        /* 副标题/导语样式 */
        .flytitle, .rubric {{
            font-family: var(--font-sans);
            font-size: 16px;
            color: #666;
            font-weight: normal;
            margin-bottom: 15px;
            line-height: 1.4;
        }}
        
        /* 段落样式 */
        p {{
            margin-bottom: 1em;
            text-align: justify;
            hyphens: auto;
        }}
        
        /* 首字母大写效果（如果原文有） */
        p.first-paragraph::first-letter {{
            float: left;
            font-size: 3.5em;
            line-height: 0.8;
            margin-right: 8px;
            margin-top: 4px;
            font-weight: bold;
        }}
        
        /* 图片样式 */
        img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 30px auto;
        }}
        
        figure {{
            margin: 30px 0;
        }}
        
        figcaption {{
            font-family: var(--font-sans);
            font-size: 14px;
            color: #666;
            text-align: center;
            margin-top: 10px;
            font-style: italic;
        }}
        
        /* 小标题 */
        h2, h3, h4 {{
            font-family: var(--font-sans);
            font-weight: bold;
            margin-top: 30px;
            margin-bottom: 15px;
            line-height: 1.3;
        }}
        
        h2 {{
            font-size: 24px;
        }}
        
        h3 {{
            font-size: 20px;
        }}
        
        /* 引用块 */
        blockquote {{
            border-left: 3px solid var(--primary-color);
            padding-left: 20px;
            margin: 20px 0;
            font-style: italic;
            color: #555;
        }}
        
        /* 链接 */
        a {{
            color: var(--primary-color);
            text-decoration: none;
        }}
        
        a:hover {{
            text-decoration: underline;
        }}
        
        /* 返回链接 */
        .back-link {{
            display: inline-block;
            margin-top: 40px;
            font-family: var(--font-sans);
            font-size: 14px;
            color: #666;
        }}
        
        /* 分隔线 */
        hr {{
            border: none;
            border-top: 1px solid var(--border-color);
            margin: 30px 0;
        }}
        
        /* 列表样式 */
        ul, ol {{
            margin-bottom: 1em;
            padding-left: 2em;
        }}
        
        li {{
            margin-bottom: 0.5em;
        }}
        
        /* 表格样式 */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-family: var(--font-sans);
            font-size: 14px;
        }}
        
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        
        th {{
            background-color: var(--secondary-bg);
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <article>
        <header class="article-header">
            <div class="section-label">{section}</div>
            <h1 class="article-title">{title}</h1>
        </header>
        <div class="article-content">
            {html_content}
        </div>
        <a href="../index.html" class="back-link">← Back to index</a>
    </article>
</body>
</html>
"""

    with open(f"output/{path}", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

def generate_index(sections):
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Economist - Weekly Edition</title>
    <style>
        :root {
            --primary-color: #E3120B;
            --text-color: #333;
            --bg-color: #fff;
            --secondary-bg: #f9f9f9;
            --border-color: #e0e0e0;
            --font-serif: "Times New Roman", Times, Georgia, serif;
            --font-sans: "Helvetica Neue", Helvetica, Arial, sans-serif;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: var(--font-sans);
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
        }
        
        /* 头部样式 */
        header {
            background-color: var(--primary-color);
            color: white;
            padding: 30px 20px;
            text-align: center;
            border-bottom: 4px solid #b00;
        }
        
        h1 {
            font-family: var(--font-serif);
            font-size: 42px;
            font-weight: normal;
            letter-spacing: -1px;
        }
        
        .subtitle {
            font-size: 14px;
            margin-top: 10px;
            opacity: 0.9;
            text-transform: uppercase;
            letter-spacing: 2px;
        }
        
        /* 主内容区 */
        main {
            max-width: 900px;
            margin: 0 auto;
            padding: 40px 20px;
        }
        
        /* Section 样式 */
        .section {
            margin-bottom: 50px;
        }
        
        .section-header {
            border-bottom: 3px solid var(--primary-color);
            padding-bottom: 10px;
            margin-bottom: 20px;
        }
        
        .section-title {
            font-family: var(--font-serif);
            font-size: 24px;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--primary-color);
        }
        
        /* 文章列表 */
        .article-list {
            list-style: none;
        }
        
        .article-item {
            padding: 15px 0;
            border-bottom: 1px solid var(--border-color);
            transition: background-color 0.2s;
        }
        
        .article-item:hover {
            background-color: var(--secondary-bg);
            margin: 0 -10px;
            padding-left: 10px;
            padding-right: 10px;
        }
        
        .article-item:last-child {
            border-bottom: none;
        }
        
        .article-link {
            text-decoration: none;
            color: var(--text-color);
            display: block;
        }
        
        .article-link:hover {
            color: var(--primary-color);
        }
        
        .article-title-text {
            font-family: var(--font-serif);
            font-size: 20px;
            font-weight: normal;
            line-height: 1.3;
        }
        
        /* 页脚 */
        footer {
            text-align: center;
            padding: 40px 20px;
            color: #666;
            font-size: 14px;
            border-top: 1px solid var(--border-color);
            margin-top: 60px;
        }
    </style>
</head>
<body>
    <header>
        <h1>The Economist</h1>
        <div class="subtitle">Weekly Edition</div>
    </header>
    
    <main>
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
            html += f'''                <li class="article-item">
                    <a href="{article["path"]}" class="article-link">
                        <div class="article-title-text">{article["title"]}</div>
                    </a>
                </li>
'''
        
        html += '''            </ul>
        </section>
'''

    html += """    </main>
    
    <footer>
        <p>Automatically generated from The Economist EPUB</p>
    </footer>
</body>
</html>
"""

    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

if __name__ == "__main__":
    main()
