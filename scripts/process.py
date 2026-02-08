#!/usr/bin/env python3
import os
import sys
import zipfile
import shutil
import re
from datetime import datetime
from bs4 import BeautifulSoup, NavigableString

def main():
    print("=" * 50)
    print("Starting EPUB processing...")
    print("=" * 50)
    
    # 清理
    if os.path.exists('output'):
        shutil.rmtree('output')
    if os.path.exists('temp_epub'):
        shutil.rmtree('temp_epub')
    
    os.makedirs('output/articles', exist_ok=True)
    os.makedirs('output/images', exist_ok=True)
    
    # 解压
    print("Extracting EPUB...")
    with zipfile.ZipFile('input/economist.epub', 'r') as z:
        z.extractall('temp_epub')
    
    # 复制图片
    copy_images('temp_epub', 'output/images')
    
    # 第一步：读取目录页，获取 section 顺序
    sections_order = get_sections_order('temp_epub')
    print(f"\nFound sections in order: {sections_order}")
    
    # 第二步：按顺序处理每个文件
    all_articles = []
    processed_files = set()
    
    # 获取 spine 顺序（EPUB 阅读顺序）
    spine_files = get_spine_order('temp_epub')
    print(f"Spine files: {len(spine_files)}")
    
    for filepath in spine_files:
        if filepath in processed_files:
            continue
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 检查是否是 Economist 内容
            if 'The Economist' not in content and 'economist.com' not in content:
                continue
            
            articles = parse_html_file(content, filepath, sections_order)
            all_articles.extend(articles)
            processed_files.add(filepath)
            
        except Exception as e:
            print(f"Error in {os.path.basename(filepath)}: {e}")
    
    print(f"\nTotal articles: {len(all_articles)}")
    
    if not all_articles:
        print("ERROR: No articles found!")
        sys.exit(1)
    
    # 去重（按 slug）
    seen = set()
    unique_articles = []
    for art in all_articles:
        if art['slug'] not in seen:
            seen.add(art['slug'])
            unique_articles.append(art)
    
    print(f"Unique articles: {len(unique_articles)}")
    
    # 生成网站
    generate_index(unique_articles, sections_order)
    generate_rss(unique_articles)
    
    shutil.rmtree('temp_epub')
    print(f"\nSuccess! Generated {len(unique_articles)} articles")

def get_sections_order(epub_root):
    """从目录页获取 section 顺序"""
    sections = []
    
    # 找目录文件
    toc_files = ['nav.xhtml', 'toc.ncx', 'toc.html', 'book_toc.html']
    
    for toc_file in toc_files:
        toc_path = find_file(epub_root, toc_file)
        if toc_path:
            try:
                with open(toc_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                soup = BeautifulSoup(content, 'html.parser')
                
                # 找所有链接文本
                for link in soup.find_all('a'):
                    text = link.get_text(strip=True)
                    # 检查是否是 section 名称
                    if text and len(text) < 100 and not text.startswith('http'):
                        # 排除广告和无关内容
                        if any(keyword in text.lower() for keyword in 
                               ['the world this week', 'leaders', 'letters', 'by invitation', 
                                'briefing', 'united states', 'the americas', 'asia', 'china',
                                'middle east', 'africa', 'europe', 'britain', 'international',
                                'business', 'finance', 'science', 'technology', 'culture',
                                'economic', 'financial indicators', 'obituary']):
                            if text not in sections:
                                sections.append(text)
                
                if sections:
                    break
                    
            except Exception as e:
                print(f"Error reading toc: {e}")
    
    return sections

def get_spine_order(epub_root):
    """获取 EPUB 的阅读顺序"""
    files = []
    
    # 找 content.opf
    opf_path = find_file(epub_root, '.opf')
    if opf_path:
        try:
            with open(opf_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析 spine
            import xml.etree.ElementTree as ET
            root = ET.fromstring(content)
            
            # 找 manifest
            manifest = {}
            for item in root.findall('.//{http://www.idpf.org/2007/opf}item'):
                item_id = item.get('id')
                item_href = item.get('href')
                if item_id and item_href:
                    manifest[item_id] = os.path.join(os.path.dirname(opf_path), item_href)
            
            # 找 spine
            for itemref in root.findall('.//{http://www.idpf.org/2007/opf}itemref'):
                item_id = itemref.get('idref')
                if item_id in manifest:
                    files.append(manifest[item_id])
            
        except Exception as e:
            print(f"Error parsing spine: {e}")
    
    # 如果 spine 解析失败，按文件名排序
    if not files:
        for root, dirs, filenames in os.walk(epub_root):
            for f in filenames:
                if f.endswith(('.html', '.xhtml', '.htm')):
                    files.append(os.path.join(root, f))
        files.sort()
    
    return files

def parse_html_file(html_content, filepath, sections_order):
    """解析 HTML 文件"""
    articles = []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 移除 script 和 style
    for tag in soup(['script', 'style']):
        tag.decompose()
    
    # 获取 body
    body = soup.find('body')
    if not body:
        return articles
    
    # 策略1：找 section 标记（如 "Leaders | Greenback danger"）
    # 策略2：按 h1/h2 结构解析
    
    full_text = body.get_text('\n', strip=True)
    
    # 尝试识别 section 和标题
    # 模式：Section Name | Subtitle（可能在 h1, h2, 或普通文本）
    
    # 先找明确的 section 标记
    section_pattern = r'(The world this week|Leaders|Letters|By Invitation|Briefing|United States|The Americas|Asia|China|Middle East & Africa|Europe|Britain|International|Business|Finance & economics|Science & technology|Culture|Economic & financial indicators|Obituary)\s*\|\s*([^\n]+)'
    
    matches = list(re.finditer(section_pattern, full_text, re.IGNORECASE))
    
    if matches:
        # 按 section 分割文章
        for i, match in enumerate(matches):
            section_name = match.group(1).strip()
            subtitle = match.group(2).strip()
            
            # 提取这段内容
            start = match.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(full_text)
            section_text = full_text[start:end]
            
            # 解析这篇文章
            article = parse_article_text(section_text, section_name, subtitle)
            if article:
                articles.append(article)
                print(f"  ✓ [{section_name}] {article['title'][:50]}...")
    
    else:
        # 没有 section 标记，尝试从 HTML 结构解析
        # 找 h1 作为主标题
        h1 = body.find('h1')
        if h1:
            title = h1.get_text(strip=True)
            
            # 找日期（可能在 h2, h3, 或后面的文本）
            date = ""
            for tag in h1.find_next_siblings(['h2', 'h3', 'p']):
                text = tag.get_text(strip=True)
                if re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}', text):
                    date = text
                    break
            
            # 获取内容（保留 HTML 结构）
            content_html = get_content_html(h1)
            
            if len(content_html) > 200:
                article = create_article(title, date, "", content_html)
                if article:
                    articles.append(article)
                    print(f"  ✓ [No section] {title[:50]}...")
    
    return articles

def parse_article_text(text, section_name, subtitle):
    """从文本解析单篇文章"""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    if not lines:
        return None
    
    # 第一行通常是主标题（大写开头，较长）
    # 但需要排除日期
    title = ""
    date = ""
    content_start = 0
    
    for i, line in enumerate(lines):
        # 跳过 subtitle 重复
        if line == subtitle or subtitle in line:
            continue
        
        # 检查是否是日期
        if re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(st|nd|rd|th)?\s+202[56]', line):
            date = line
            content_start = i + 1
            continue
        
        # 找标题（不是日期，长度适中，大写开头）
        if not title and len(line) > 10 and len(line) < 200 and line[0].isupper():
            # 检查不是纯日期
            if not re.match(r'^\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)', line):
                title = line
                content_start = i + 1
                continue
    
    # 如果没找到标题，用 subtitle
    if not title:
        title = subtitle
    
    # 如果还是没标题，跳过
    if not title or title == date:
        return None
    
    # 提取内容
    content_lines = lines[content_start:]
    
    # 清理内容（保留段落）
    content = '\n\n'.join(content_lines)
    
    # 移除下载信息
    content = re.sub(r'This article was downloaded by zlibrary from https?://\S+', '', content)
    
    if len(content) < 100:
        return None
    
    return create_article(title, date, section_name, content)

def get_content_html(start_tag):
    """获取从 start_tag 之后的内容 HTML"""
    content = []
    
    for sibling in start_tag.find_next_siblings():
        # 如果遇到新的 h1，停止
        if sibling.name == 'h1':
            break
        
        # 保留标签
        content.append(str(sibling))
    
    return '\n'.join(content)

def create_article(title, date, section, content):
    """创建文章文件"""
    
    # 清理标题
    title = re.sub(r'\s+', ' ', title).strip()
    if len(title) > 150:
        title = title[:147] + "..."
    
    # 如果标题是日期，尝试用 section 或其他信息
    if re.match(r'^\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)', title):
        if section:
            title = f"{section} - {title}"
        else:
            title = "Article - " + title
    
    # 生成 slug
    slug = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '-').lower()[:50]
    slug = re.sub(r'-+', '-', slug)
    
    # 确保唯一
    base_slug = slug
    counter = 1
    while os.path.exists(f'output/articles/{slug}.html'):
        slug = f"{base_slug}-{counter}"
        counter += 1
    
    # 处理内容
    # 如果是纯文本，转换为段落
    if not content.strip().startswith('<'):
        paragraphs = content.split('\n\n')
        paragraphs = [f'<p>{p.strip()}</p>' for p in paragraphs if p.strip()]
        content = '\n'.join(paragraphs)
    
    # 修复图片路径
    content = re.sub(r'src=["\']static_images/', 'src="/images/', content)
    content = re.sub(r'src=["\']../static_images/', 'src="/images/', content)
    content = re.sub(r'src=["\']../../static_images/', 'src="/images/', content)
    
    art_path = f'articles/{slug}.html'
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} | The Economist</title>
    <style>
        body {{
            max-width: 720px;
            margin: 0 auto;
            padding: 40px 20px;
            font-family: Georgia, "Times New Roman", serif;
            font-size: 18px;
            line-height: 1.6;
            color: #222;
        }}
        .section {{
            color: #e3120b;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }}
        h1 {{
            font-size: 32px;
            margin: 0 0 10px 0;
            line-height: 1.2;
            font-weight: normal;
        }}
        .date {{
            color: #666;
            font-size: 14px;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #ddd;
        }}
        p {{
            margin: 0 0 1em 0;
            text-align: justify;
        }}
        img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 20px auto;
        }}
        a {{
            color: #e3120b;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    {f'<div class="section">{section}</div>' if section else ''}
    <h1>{title}</h1>
    {f'<div class="date">{date}</div>' if date else ''}
    {content}
</body>
</html>'''
    
    with open(f'output/{art_path}', 'w', encoding='utf-8') as f:
        f.write(html)
    
    return {
        'title': title,
        'slug': slug,
        'path': art_path,
        'date': datetime.now().isoformat(),
        'section': section
    }

def generate_index(articles, sections_order):
    """生成索引页，保持 section 顺序"""
    repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
    username, repo_name = repo.split('/')
    base_url = f"https://{username}.github.io/{repo_name}"
    
    # 按 section 分组，保持顺序
    by_section = {}
    section_positions = {}
    
    for art in articles:
        sec = art.get('section', 'Other')
        if sec not in by_section:
            by_section[sec] = []
        by_section[sec].append(art)
    
    # 确定 section 顺序
    ordered_sections = []
    
    # 先按 sections_order 中的顺序
    for sec in sections_order:
        # 模糊匹配
        for key in by_section.keys():
            if sec.lower() in key.lower() or key.lower() in sec.lower():
                if key not in ordered_sections:
                    ordered_sections.append(key)
                    section_positions[key] = len(ordered_sections)
    
    # 添加剩余的 section
    for key in by_section.keys():
        if key not in ordered_sections:
            ordered_sections.append(key)
            section_positions[key] = 999
    
    # 对每个 section 内的文章，保持原始顺序（按文件处理顺序）
    # articles 列表已经是按顺序的，所以 by_section 中的顺序也是对的
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>The Economist Weekly</title>
    <style>
        body {{
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #e3120b;
            margin-bottom: 8px;
        }}
        .subtitle {{
            color: #666;
            margin-bottom: 30px;
        }}
        .section-title {{
            color: #e3120b;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin: 30px 0 15px 0;
            padding-bottom: 5px;
            border-bottom: 2px solid #e3120b;
        }}
        .article {{
            border-bottom: 1px solid #eee;
            padding: 12px 0;
        }}
        .article:hover {{
            background: #fafafa;
            margin: 0 -40px;
            padding-left: 40px;
            padding-right: 40px;
        }}
        .article a {{
            color: #222;
            text-decoration: none;
            font-size: 16px;
            display: block;
        }}
        .article a:hover {{
            color: #e3120b;
        }}
        .rss {{
            display: inline-block;
            margin-top: 30px;
            padding: 12px 24px;
            background: #e3120b;
            color: white;
            text-decoration: none;
            border-radius: 6px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>The Economist</h1>
        <div class="subtitle">{len(articles)} articles • Updated {datetime.now().strftime("%Y-%m-%d")}</div>
'''
    
    for sec in ordered_sections:
        if sec in by_section and by_section[sec]:
            html += f'<div class="section-title">{sec}</div>\n'
            for art in by_section[sec]:
                html += f'<div class="article"><a href="{art["path"]}">{art["title"]}</a></div>\n'
    
    html += f'''
        <a href="feed.xml" class="rss">📡 Subscribe via RSS</a>
    </div>
</body>
</html>'''
    
    with open('output/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

def generate_rss(articles):
    """生成 RSS"""
    repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
    username, repo_name = repo.split('/')
    base_url = f"https://{username}.github.io/{repo_name}"
    
    items = []
    for art in articles[:30]:
        try:
            with open(f'output/{art["path"]}', 'r', encoding='utf-8') as f:
                content = f.read()
            
            match = re.search(r'<body>(.*?)</body>', content, re.DOTALL)
            body = match.group(1) if match else content
            
            items.append(f'''
    <item>
      <title><![CDATA[{art["title"]}]]></title>
      <link>{base_url}/{art["path"]}</link>
      <guid>{base_url}/{art["path"]}</guid>
      <description><![CDATA[{art.get("section", "")} - {art["title"]}]]></description>
      <content:encoded xmlns:content="http://purl.org/rss/1.0/modules/content/">
        <![CDATA[{body}]]>
      </content:encoded>
    </item>''')
        except Exception as e:
            print(f"Warning: RSS error for {art['title']}: {e}")
    
    rss = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:content="http://purl.org/rss/1.0/modules/content/" version="2.0">
  <channel>
    <title>The Economist Weekly</title>
    <link>{base_url}/</link>
    <description>Full-text articles from The Economist</description>
    <language>en</language>
    <lastBuildDate>{datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>
    {''.join(items)}
  </channel>
</rss>'''
    
    with open('output/feed.xml', 'w', encoding='utf-8') as f:
        f.write(rss)
    
    print(f"RSS: {base_url}/feed.xml")

def find_file(root, filename):
    """查找文件"""
    for r, d, files in os.walk(root):
        for f in files:
            if f == filename or f.endswith(filename):
                return os.path.join(r, f)
    return None

def copy_images(source_dir, output_dir):
    """复制图片"""
    for r, dirs, files in os.walk(source_dir):
        if 'images' in r.lower():
            for f in files:
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp')):
                    src = os.path.join(r, f)
                    dst = os.path.join(output_dir, f)
                    shutil.copy2(src, dst)

if __name__ == '__main__':
    main()
