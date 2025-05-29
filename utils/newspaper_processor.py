import logging
import re
from typing import Optional
from readabilipy import simple_json_from_html_string
from markdownify import markdownify as html2md
import bs4

logger = logging.getLogger(__name__)

SPECIAL_HEADER = "#####&#009;\n\n######&#009;\n\n####&#009;\n\n"
EMAIL_REGEX = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4}\b", re.I)
# Match any Markdown link to /tema/...
TOPIC_LINK_REGEX = re.compile(r'\[([^\]]+)\]\(/tema/[^)]+\)')

# Also match links with a title (e.g. [text](/tema/... "title"))
TOPIC_LINK_WITH_TITLE_REGEX = re.compile(r'\[([^\]]+)\]\(/tema/[^)]+\s+"[^"]*"\)')

# Match image markdown format ![text](url)
IMAGE_MARKDOWN_REGEX = re.compile(r'!\[([^\]]+)\]\(([^)]+)\)')

# Match URLs in markdown links
URL_REGEX = re.compile(r'\[([^\]]+)\]\((https?://[^)]+)\)')

def replace_ru_domains(text: str) -> str:
    """Replace any .ru domain links with example.com."""
    def replace_url(match):
        text, url = match.groups()
        if '.ru' in url:
            return f'[{text}](https://example.com)'
        return match.group(0)
    
    return URL_REGEX.sub(replace_url, text)

def extract_article_text(html_content: str, signature: str) -> Optional[str]:
    """
    Extract the main article text from raw HTML content, sanitize, convert to Markdown, and sign it.
    Returns a Markdown string. The signature parameter is required and will be appended as HTML before Markdown conversion.
    """
    try:
        # Use readabilipy to extract the main content
        try:
            article = simple_json_from_html_string(html_content, use_readability=True)
            
            # Extract content from the article
            if article and 'content' in article and article['content']:
                html = article['content']
            else:
                logger.warning("No content found in article")
                return None

            # Remove emails from the HTML content
            html = EMAIL_REGEX.sub(lambda m: m.group(0).replace('@', ' at '), html)

            # Convert main content to Markdown (preserve links)
            markdown = html2md(html)
            markdown = markdown.strip()

            # Replace .ru domain links with example.com
            markdown = replace_ru_domains(markdown)

            # Prepare blockquoted title (with image link if available)
            title_line = None
            image_url = None
            # Try to get og:image from the HTML meta tag
            soup = bs4.BeautifulSoup(html_content, "html.parser")
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                image_url = og_image["content"]
            # Fallback to readabilipy's image fields if not found
            if not image_url:
                for key in ['lead_image_url', 'image', 'url']:
                    if key in article and article[key]:
                        image_url = article[key]
                        break
            if 'title' in article and article['title']:
                title = article['title'].strip()
                if image_url:
                    title_line = f"> # [{title}]({image_url})"
                else:
                    title_line = f"> # {title}"

            # Blockquote only the main article content, preserving blank lines and indentation
            # Skip all leading blank lines
            content_lines = markdown.splitlines()
            while content_lines and content_lines[0].strip() == '':
                content_lines.pop(0)

            blockquoted_lines = []
            if title_line:
                blockquoted_lines.append(title_line)
                blockquoted_lines.append('>   ')
                blockquoted_lines.append('>   ')
                blockquoted_lines.append('>   ')
            for line in content_lines:
                if line.strip() == '':
                    blockquoted_lines.append('>   ')
                else:
                    # Convert topic links to simple text
                    line = TOPIC_LINK_WITH_TITLE_REGEX.sub(r'\1', line)
                    line = TOPIC_LINK_REGEX.sub(r'\1', line)
                    # Convert image markdown to link format
                    line = IMAGE_MARKDOWN_REGEX.sub(r'[\1](\2)', line)
                    # Convert horizontal rules
                    line = line.replace('---', '- - - - - -')
                    blockquoted_lines.append('> ' + line)

            # Remove trailing horizontal rules and blank lines before the signature
            while blockquoted_lines and (blockquoted_lines[-1].strip() in ('> - - - - - -', '>   ', '>')):
                blockquoted_lines.pop()
            # Add the last horizontal rule
            blockquoted_lines.append('> - - - - - -')

            blockquoted = '\n'.join(blockquoted_lines)

            # Convert signature to Markdown separately, preserving links
            signature_md = html2md(signature).strip()
            # Remove leading horizontal rule if present
            signature_lines = signature_md.splitlines()
            if signature_lines and signature_lines[0].strip() == '---':
                signature_md = '\n'.join(signature_lines[1:]).lstrip()

            # Replace .ru domain links in signature
            signature_md = replace_ru_domains(signature_md)

            # Add special header, blockquoted content, two blank lines, horizontal rule, one blank line, and signature
            result = f"{SPECIAL_HEADER}{blockquoted}\n\n\n- - - - - -\n\n{signature_md}"
            return result

        except Exception as e:
            logger.warning(f"Failed to extract text with readabilipy: {e}")

        logger.warning("Could not find article content in HTML")
        return None

    except Exception as e:
        logger.error(f"Error processing article HTML: {e}")
        return None 