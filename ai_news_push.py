import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable


WECHAT_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WECHAT_TEMPLATE_URL = "https://api.weixin.qq.com/cgi-bin/message/template/send"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36 ai-news-wechat-bot/1.0"
)

AI_KEYWORDS = (
    "ai",
    "artificial intelligence",
    "openai",
    "chatgpt",
    "gpt",
    "llm",
    "large language model",
    "anthropic",
    "claude",
    "google deepmind",
    "gemini",
    "mistral",
    "llama",
    "nvidia",
    "machine learning",
    "deep learning",
    "agent",
    "人工智能",
    "大模型",
    "生成式",
    "模型",
    "智能体",
)


@dataclass(frozen=True)
class NewsItem:
    title: str
    link: str
    published: dt.datetime | None
    source: str
    tier: str = "media"
    summary: str = ""


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


def http_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict | None = None,
    timeout: int = 30,
) -> dict | str:
    data = None
    request_headers = {"User-Agent": DEFAULT_USER_AGENT, **(headers or {})}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **request_headers}

    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc

    content_type = response.headers.get("Content-Type", "")
    if "json" in content_type:
        return json.loads(body)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def load_sources(path: str) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    sources = data.get("sources", [])
    if not sources:
        raise RuntimeError(f"No sources configured in {path}")
    return sources


def parse_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None

    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = None

    if parsed is None:
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                parsed = dt.datetime.strptime(value, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def xml_text(element: ET.Element, names: Iterable[str]) -> str:
    for name in names:
        node = element.find(name)
        if node is not None and node.text:
            return html.unescape(node.text.strip())
    return ""


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def fetch_rss(source: dict[str, str]) -> list[NewsItem]:
    body = http_request(source["url"], headers={"User-Agent": "ai-news-wechat-bot/1.0"})
    if not isinstance(body, str):
        body = json.dumps(body, ensure_ascii=False)

    root = ET.fromstring(body)
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    parsed_items: list[NewsItem] = []
    for item in items:
        title = xml_text(item, ("title", "{http://www.w3.org/2005/Atom}title"))
        link = xml_text(item, ("link", "{http://www.w3.org/2005/Atom}link"))
        atom_link = item.find("{http://www.w3.org/2005/Atom}link")
        if not link and atom_link is not None:
            link = atom_link.attrib.get("href", "")
        published = parse_datetime(
            xml_text(
                item,
                (
                    "pubDate",
                    "published",
                    "updated",
                    "{http://www.w3.org/2005/Atom}published",
                    "{http://www.w3.org/2005/Atom}updated",
                ),
            )
        )
        summary = strip_html(
            xml_text(
                item,
                (
                    "description",
                    "summary",
                    "content",
                    "{http://www.w3.org/2005/Atom}summary",
                    "{http://www.w3.org/2005/Atom}content",
                ),
            )
        )
        if title and link:
            parsed_items.append(
                NewsItem(
                    title=strip_html(title),
                    link=link.strip(),
                    published=published,
                    source=source.get("name", "RSS"),
                    tier=source.get("tier", "media"),
                    summary=summary,
                )
            )
    return parsed_items


def yesterday_range(local_tz: dt.tzinfo) -> tuple[dt.datetime, dt.datetime, dt.date]:
    now = dt.datetime.now(local_tz)
    target_date = now.date() - dt.timedelta(days=1)
    start = dt.datetime.combine(target_date, dt.time.min, tzinfo=local_tz)
    end = start + dt.timedelta(days=1)
    return start.astimezone(dt.timezone.utc), end.astimezone(dt.timezone.utc), target_date


def is_ai_related(item: NewsItem) -> bool:
    haystack = f"{item.title} {item.summary}".lower()
    return any(keyword in haystack for keyword in AI_KEYWORDS)


def filter_items(items: list[NewsItem], start: dt.datetime, end: dt.datetime) -> list[NewsItem]:
    seen: set[str] = set()
    filtered: list[NewsItem] = []
    for item in items:
        key = item.link.split("?")[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        if item.published is not None and not (start <= item.published < end):
            continue
        if not is_ai_related(item):
            continue
        filtered.append(item)
    tier_rank = {"official": 0, "developer": 1, "analysis": 2, "industry": 3, "cn": 4, "media": 5}
    return sorted(
        filtered,
        key=lambda x: (
            tier_rank.get(x.tier, 9),
            -(x.published or dt.datetime.min.replace(tzinfo=dt.timezone.utc)).timestamp(),
        ),
    )


def summarize_with_openai(items: list[NewsItem], target_date: dt.date) -> str:
    api_key = env("OPENAI_API_KEY")
    base_url = env("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).rstrip("/")
    model = env("OPENAI_MODEL", "gpt-4.1-mini")
    max_items = int(env("MAX_NEWS_ITEMS", "5"))
    selected = items[:max_items]
    fallback = format_without_ai(selected, target_date)
    if not api_key:
        return fallback
    if api_key.startswith("wx"):
        raise RuntimeError(
            "OPENAI_API_KEY looks like a WeChat appID. "
            "Do not put WECHAT_APP_ID into OPENAI_API_KEY. "
            "Unset OPENAI_API_KEY for title-only dry runs, or use a real OpenAI API key from https://platform.openai.com/api-keys."
        )

    source_text = "\n".join(
        f"{idx}. 标题：{item.title}\n来源：{item.source}\n来源级别：{item.tier}\n摘要：{item.summary[:400]}\n链接：{item.link}"
        for idx, item in enumerate(selected, start=1)
    )
    prompt = f"""
你是给个人读者推送的 AI 新闻编辑。请基于下面新闻，生成一份中文微信晨报。

要求：
- 日期是 {target_date.isoformat()} 的昨日 AI 新闻。
- 最多保留 {max_items} 条。
- 每条只输出两行：第一行是“序号. 标题”，第二行是“一句话影响判断”。
- 不要输出链接，不要输出来源，不要输出长摘要。
- 每条影响判断不超过 35 个中文字符。
- 优先保留官方发布、开发者生态、严肃分析；弱化转载、融资噪音、纯观点水文。
- 删除低价值、重复、营销味重的内容。
- 不要编造新闻里没有的信息。
- 输出适合直接在微信模板消息里阅读，简洁但有判断。

新闻：
{source_text}
""".strip()

    try:
        response = http_request(
            f"{base_url}/chat/completions",
            method="POST",
            headers={"Authorization": f"Bearer {api_key}"},
            payload={
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是严格、克制、重视信息密度的中文 AI 新闻编辑。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            },
            timeout=60,
        )
    except Exception as exc:
        print(f"Warning: AI summarization failed, using fallback digest: {exc}", file=sys.stderr)
        return fallback
    if not isinstance(response, dict):
        return fallback
    return response["choices"][0]["message"]["content"].strip()


def format_without_ai(items: list[NewsItem], target_date: dt.date) -> str:
    if not items:
        return f"{target_date.isoformat()} 没有抓到符合条件的昨日 AI 新闻。"
    lines = []
    for idx, item in enumerate(items, start=1):
        lines.append(f"{idx}. {item.title}")
        lines.append(compact_impact(item))
        lines.append("")
    return "\n".join(lines).strip()


def compact_impact(item: NewsItem) -> str:
    text = item.summary.strip() if item.summary else ""
    if text:
        text = re.sub(r"\s+", " ", text)
        return text[:45].rstrip() + ("..." if len(text) > 45 else "")
    if item.tier == "official":
        return "官方发布，值得优先关注后续影响。"
    if item.tier == "developer":
        return "开发者生态变化，可能影响工具选择。"
    if item.tier == "analysis":
        return "偏趋势分析，适合判断行业方向。"
    return "行业动态，适合快速了解市场变化。"


def truncate_wechat_value(value: str, limit: int = 1800) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 20].rstrip() + "\n...(内容过长已截断)"


def get_wechat_access_token() -> str:
    app_id = env("WECHAT_APP_ID", required=True)
    app_secret = env("WECHAT_APP_SECRET", required=True)
    url = f"{WECHAT_TOKEN_URL}?grant_type=client_credential&appid={urllib.parse.quote(app_id)}&secret={urllib.parse.quote(app_secret)}"
    response = http_request(url)
    if not isinstance(response, dict) or "access_token" not in response:
        raise RuntimeError(f"Failed to get WeChat access token: {response}")
    return response["access_token"]


def push_wechat(content: str, target_date: dt.date) -> dict:
    token = get_wechat_access_token()
    url = f"{WECHAT_TEMPLATE_URL}?access_token={urllib.parse.quote(token)}"
    payload = {
        "touser": env("WECHAT_OPENID", required=True),
        "template_id": env("WECHAT_TEMPLATE_ID", required=True),
        "data": {
            "first": {"value": "昨日 AI 新闻晨报", "color": "#173177"},
            "keyword1": {"value": target_date.isoformat(), "color": "#173177"},
            "keyword2": {"value": "AI 新闻汇总", "color": "#173177"},
            "keyword3": {"value": truncate_wechat_value(content, 900), "color": "#111111"},
            "remark": {"value": "以上为自动筛选摘要，建议只读重点条目。", "color": "#666666"},
        },
    }
    response = http_request(url, method="POST", payload=payload)
    if not isinstance(response, dict) or response.get("errcode") != 0:
        if isinstance(response, dict) and response.get("errcode") == 40037:
            raise RuntimeError(
                "WeChat push failed: invalid WECHAT_TEMPLATE_ID. "
                "Use the template_id generated in the same WeChat sandbox/test account as WECHAT_APP_ID. "
                "Do not use the template title, template content, or a template_id from another account. "
                f"Raw response: {response}"
            )
        raise RuntimeError(f"WeChat push failed: {response}")
    return response


def main() -> int:
    source_path = env("NEWS_SOURCES_FILE", "news_sources.json")
    tz = dt.timezone(dt.timedelta(hours=int(env("LOCAL_TIMEZONE_HOURS", "8"))))
    start, end, target_date = yesterday_range(tz)

    all_items: list[NewsItem] = []
    for source in load_sources(source_path):
        try:
            all_items.extend(fetch_rss(source))
        except Exception as exc:
            print(f"Warning: failed to fetch {source.get('name', source.get('url'))}: {exc}", file=sys.stderr)

    items = filter_items(all_items, start, end)
    max_items = int(env("MAX_NEWS_ITEMS", "5"))
    content = summarize_with_openai(items[:max_items], target_date)

    if env("DRY_RUN", "0") == "1":
        print(content)
    else:
        print(textwrap.shorten(content.replace("\n", " "), width=500, placeholder="..."))
    if env("DRY_RUN", "0") == "1":
        print("\nDRY_RUN=1, skipped WeChat push.")
        return 0

    result = push_wechat(content, target_date)
    print(f"WeChat push succeeded: msgid={result.get('msgid')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
