import os
import zipfile
import shutil
import re
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

INPUT_EPUB = "input/economist.epub"

# 定义需要保留的 Section（注意：这里使用了小写进行标准化匹配，以防大小写差异）
# 修正了你原来拼写的 "by invitatation" -> "by invitation"
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
    # 清理旧数据
    shutil.rmtree("temp_epub", ignore_errors=True)
    shutil.rmtree("output", ignore_errors=True)

    # 创建目录
    os.makedirs("temp_epub", exist_ok=True)
    os.makedirs("output/articles", exist_ok=True)
    os.makedirs("output/images", exist_ok=True)
    os.makedirs("output/css", exist_ok=True)

    # 解压并处理资源
    unzip_epub()
    copy_images()
    css_filename = copy_css()  # 提取CSS并获取文件名

    # 获取正确的阅读顺序
    ordered_files = get_reading_order("temp_epub")
    
    articles = []
    current_section = "Other"

    # 按顺序解析文件
    for html_file in ordered_files:
        full_path = os.path.join("temp_epub", html_file)
        if not os.path.exists(full_path):
            continue
            
        # 传入当前的 section，并接收更新后的 section
        new_articles, current_section = parse_html_content(full_path, current_section, css_filename)
        
        # 过滤文章
        for art in new_articles:
            # 简单的归一化匹配：转小写，去除首尾空格
            sec_norm = art['section'].strip().lower()
            if sec_norm in ALLOWED_SECTIONS:
                articles.append(art)

    generate_index(articles)

    print(f"Done. Extracted {len(articles)} articles from {len(ALLOWED_SECTIONS)} sections.")


# --------------------------------------------------

def unzip_epub():
    with zipfile.ZipFile(INPUT_EPUB, "r") as z:
        z.extractall("temp_epub")


# --------------------------------------------------

def get_reading_order(base_dir):
    """
    解析 content.opf 文件，获取 spine 中的阅读顺序对应的 HTML 文件路径列表。
    """
    opf_path = None
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.endswith(".opf"):
                opf_path = os.path.join(root, f)
                break
        if opf_path:
            break
            
    if not opf_path:
        return []

    # 解析 XML
    # 注意：EPUB XML 通常带有命名空间，解析时需要处理
    try:
        tree = ET.parse(opf_path)
        root = tree.getroot()
        
        # 提取命名空间
        ns = {'opf': 'http://www.idpf.org/2007/opf'}
        
        # 获取 Manifest (id -> href)
        manifest = {}
        for item in root.findall(".//opf:item", ns):
            manifest[item.get("id")] = item.get("href")
            
        # 获取 Spine (顺序的 idref)
        spine_ids = []
        for itemref in root.findall(".//opf:itemref", ns):
            spine_ids.append(itemref.get("idref"))
            
        # 转换为文件路径 (相对于 opf 文件的位置)
        opf_dir = os.path.dirname(opf_path)
        ordered_files = []
        for spin_id in spine_ids:
            href = manifest.get(spin_id)
            if href:
                # 处理相对路径
                full_path = os.path.join(opf_dir, href)
                # 转换为相对于 base_dir 的路径，方便后续调用
                rel_path = os.path.relpath(full_path, base_dir)
                ordered_files.append(rel_path)
                
        return ordered_files
    except Exception as e:
        print(f"Error parsing OPF: {e}")
        return []


# --------------------------------------------------

def copy_images():
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp")):
                src = os.path.join(root, f)
                dst = os.path.join("output/images", f)
                # 扁平化存储图片，防止路径层级太深
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)

def copy_css():
    """查找并复制 CSS 文件，返回主 CSS 文件名"""
    css_name = "style.css" # 默认名
    found = False
    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.lower().endswith(".css"):
                src = os.path.join(root, f)
                dst = os.path.join("output/css", f)
                shutil.copy2(src, dst)
                css_name = f
                found = True
                # 这里我们假设第一个找到的 css 是主样式，或者全部拷贝
                # 通常 Economist epub 只有一个主要的 css
    return css_name if found else None


# --------------------------------------------------

def parse_html_content(filepath, current_section, css_filename):
    """
    解析单个 HTML 文件。
    参数:
      filepath: 文件路径
      current_section: 上一个文件结束时的 section 状态
      css_filename: 用于写入文章头部
    返回:
      (articles_list, updated_current_section)
    """
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    if not body:
        return [], current_section

    articles = []
    
    # 查找所有 h1 和 h2，按在文档中出现的顺序
    tags = body.find_all(["h1", "h2"])
    
    for tag in tags:
        # Section Header
        if tag.name == "h2":
            candidate_section = tag.get_text(strip=True)
            if candidate_section:
                current_section = candidate_section
            continue

        # Article Header
        if tag.name == "h1":
            title = tag.get_text(strip=True)
            if not title:
                continue

            # 提取文章内容：从当前 h1 开始，直到下一个 h1 或 h2
            content_nodes = [tag]
            for sib in tag.next_siblings:
                if getattr(sib, "name", None) in ["h1", "h2"]:
                    break
                content_nodes.append(sib)

            article_html = "".join(str(x) for x in content_nodes)

            # 修复图片路径 (指向 ../images/)
            article_html = re.sub(
                r'src=["\']([^"\']*?/)?([^/"\']+\.(jpg|jpeg|png|gif|svg|webp))["\']',
                r'src="../images/\2"',
                article_html,
                flags=re.IGNORECASE
            )

            # 简单的长度过滤
            if len(article_html) < 200:
                continue

            slug = re.sub(r"[^\w\s-]", "", title).replace(" ", "-").lower()[:80]
            # 防止重名覆盖
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


# --------------------------------------------------

def write_article(path, html_content, title, css_filename):
    css_link = f'<link rel="stylesheet" href="../css/{css_filename}" type="text/css"/>' if css_filename else ""
    
    # 尽量保持干净的 HTML 结构，同时引入 CSS
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{css_link}
<style>
    /* 基础补充样式，防止原文CSS缺失导致布局错乱 */
    body {{ max-width: 800px; margin: 0 auto; padding: 20px; font-family: Georgia, serif; line-height: 1.6; }}
    img {{ max-width: 100%; height: auto; display: block; margin: 20px auto; }}
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


# --------------------------------------------------

def generate_index(articles):
    # 增加简单的 CSS 美化索引页
    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Economist</title>
<style>
    body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f4f4f4; }
    h1 { text-align: center; color: #e3120b; }
    h2 { border-bottom: 2px solid #e3120b; padding-bottom: 10px; margin-top: 30px; font-size: 1.2em; text-transform: uppercase; color: #333; }
    div.article-link { margin: 10px 0; padding: 10px; background: white; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    a { text-decoration: none; color: #1a1a1a; font-weight: bold; font-size: 1.1em; }
    a:hover { color: #e3120b; }
</style>
</head>
<body>
<h1>The Economist</h1>
"""

    current_section = None

    # articles 列表已经是按照书本顺序排列的了
    # 只需要在 section 变化时插入标题
    for a in articles:
        if a["section"] != current_section:
            current_section = a["section"]
            html += f"<h2>{current_section}</h2>"

        html += f'<div class="article-link"><a href="{a["path"]}">{a["title"]}</a></div>'

    html += "</body></html>"

    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

if __name__ == "__main__":
    main()
