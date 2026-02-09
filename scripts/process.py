import os
import zipfile
import shutil
import re
from bs4 import BeautifulSoup

INPUT_EPUB = "input/economist.epub"

def main():
    shutil.rmtree("temp_epub", ignore_errors=True)
    shutil.rmtree("output", ignore_errors=True)

    os.makedirs("temp_epub", exist_ok=True)
    os.makedirs("output/articles", exist_ok=True)
    os.makedirs("output/images", exist_ok=True)

    unzip_epub()
    copy_images()

    articles = []

    for root, _, files in os.walk("temp_epub"):
        for f in files:
            if f.endswith((".html", ".xhtml")):
                path = os.path.join(root, f)
                articles.extend(parse_html_file(path))

    generate_index(articles)

    print("Done. Articles:", len(articles))


# --------------------------------------------------

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

def parse_html_file(filepath):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    if not body:
        return []

    articles = []
    current_section = "Other"

    # 识别 section 标题
    for tag in body.find_all(["h1", "h2"]):

        # section header
        if tag.name == "h2":
            current_section = tag.get_text(strip=True)
            continue

        if tag.name == "h1":
            title = tag.get_text(strip=True)
            if not title:
                continue

            content_nodes = [tag]

            for sib in tag.next_siblings:
                if getattr(sib, "name", None) == "h1":
                    break
                if getattr(sib, "name", None) == "h2":
                    break
                content_nodes.append(sib)

            article_html = "".join(str(x) for x in content_nodes)

            # 修复图片路径
            article_html = re.sub(
                r'src=["\']([^"\']*?/)?([^/"\']+\.(jpg|jpeg|png|gif|svg|webp))["\']',
                r'src="../images/\2"',
                article_html,
                flags=re.IGNORECASE
            )

            if len(article_html) < 200:
                continue

            slug = re.sub(r"[^\w\s-]", "", title).replace(" ", "-").lower()[:80]
            path = f"articles/{slug}.html"

            write_article(path, article_html)

            articles.append({
                "section": current_section,
                "title": title,
                "path": path
            })

    return articles


# --------------------------------------------------

def write_article(path, html_content):
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
</head>
<body>
{html_content}
</body>
</html>
"""

    with open(f"output/{path}", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

def generate_index(articles):
    html = "<html><body><h1>Economist</h1>"

    current_section = None

    for a in articles:
        if a["section"] != current_section:
            current_section = a["section"]
            html += f"<h2>{current_section}</h2>"

        html += f'<div><a href="{a["path"]}">{a["title"]}</a></div>'

    html += "</body></html>"

    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)


# --------------------------------------------------

if __name__ == "__main__":
    main()
