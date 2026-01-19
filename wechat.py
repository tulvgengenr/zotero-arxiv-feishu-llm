from typing import Dict, List
from datetime import datetime
import requests


def _score_to_stars(score: float) -> str:
    """将相似度分数转换为星级显示"""
    if score is None:
        return "N/A"
    level = max(1, min(5, int(round(score * 5))))
    return "⭐" * level


def _short_link(url: str) -> str:
    """简化链接显示"""
    if not url:
        return ""
    link = url.replace("https://", "").replace("http://", "")
    return link.rstrip("/")


def _paper_md(idx: int, paper: Dict[str, str], max_abstract_length: int = 500) -> str:
    """将单篇论文转换为Markdown格式"""
    title = paper.get("title", "Untitled")
    link = paper.get("link") or paper.get("url")
    score = paper.get("score")
    score_text = f"{score:.2f}" if isinstance(score, (int, float)) else "N/A"
    stars = _score_to_stars(score if isinstance(score, (int, float)) else None)
    abstract = paper.get("abstract") or ""
    abstract_zh = paper.get("abstract_zh") or ""
    tldr = paper.get("tldr") or ""
    authors = paper.get("authors") or []
    tags = paper.get("tags") or []
    keywords = ", ".join(tags[:6])
    if authors:
        if len(authors) <= 5:
            author_line = ", ".join(authors)
        else:
            author_line = ", ".join(authors[:4] + ["...", authors[-1]])
    else:
        author_line = ""
    link_text = _short_link(link)

    lines = []
    # 标题
    if link:
        lines.append(f"**{idx}. [{title}]({link})**")
    else:
        lines.append(f"**{idx}. {title}**")
    
    # 评分和链接
    score_line = f"{stars} 相关度: {score_text}"
    if link_text:
        score_line += f" | [{link_text}]({link})"
    lines.append(score_line)
    
    # 作者
    if author_line:
        lines.append(f"**作者:** {author_line}")
    
    # 关键词
    if keywords:
        lines.append(f"**关键词:** {keywords}")
    
    # TLDR或摘要（限制长度以避免单条消息过长）
    if tldr:
        tldr_text = tldr.replace('TLDR: ', '')
        if len(tldr_text) > max_abstract_length:
            tldr_text = tldr_text[:max_abstract_length] + "..."
        lines.append(f"**TLDR:** {tldr_text}")
    elif abstract_zh:
        if len(abstract_zh) > max_abstract_length:
            abstract_zh = abstract_zh[:max_abstract_length] + "..."
        lines.append(f"**摘要(中文):** {abstract_zh}")
    elif abstract:
        if len(abstract) > max_abstract_length:
            abstract = abstract[:max_abstract_length] + "..."
        lines.append(f"**摘要:** {abstract}")
    
    return "\n".join(lines)


def build_wechat_markdown(
    title: str,
    query: str,
    papers: List[Dict[str, str]],
) -> Dict:
    """构建企业微信Markdown格式的消息内容（已废弃，保留用于兼容）"""
    total = len(papers)
    date_str = datetime.now().strftime('%Y年%m月%d日')
    
    # 构建Markdown内容
    content_parts = [
        f"# {title}",
        "",
        f"ฅʕ•̫͡•ʔฅ ◔.̮◔✧ (•̀ᴗ• ) ArXiv 小助手来啦！{date_str} 找到 **{total}** 📚 篇论文：",
        "",
    ]
    
    if total == 0:
        content_parts.append("未找到匹配的论文。")
    else:
        content_parts.append("---")
        content_parts.append("")
        for idx, paper in enumerate(papers, 1):
            content_parts.append(_paper_md(idx, paper))
            if idx < total:
                content_parts.append("")
                content_parts.append("---")
                content_parts.append("")
    
    markdown_content = "\n".join(content_parts)
    
    return {
        "msgtype": "markdown",
        "markdown": {
            "content": markdown_content
        }
    }


def build_single_paper_message(
    idx: int,
    total: int,
    paper: Dict[str, str],
    title: str = "每日论文推送",
) -> Dict:
    """构建单篇论文的企业微信Markdown消息"""
    date_str = datetime.now().strftime('%Y年%m月%d日')
    
    # 构建单篇论文的Markdown内容
    header = f"# {title}\n\n📚 **第 {idx}/{total} 篇** | {date_str}\n\n"
    paper_content = _paper_md(idx, paper, max_abstract_length=800)  # 单条消息可以更长
    
    markdown_content = header + paper_content
    
    # 确保不超过4096字符限制
    MAX_LENGTH = 4096
    if len(markdown_content) > MAX_LENGTH:
        # 如果还是太长，截断摘要部分
        paper_content_short = _paper_md(idx, paper, max_abstract_length=300)
        markdown_content = header + paper_content_short
        if len(markdown_content) > MAX_LENGTH:
            markdown_content = markdown_content[:MAX_LENGTH - 10] + "..."
    
    return {
        "msgtype": "markdown",
        "markdown": {
            "content": markdown_content
        }
    }


def build_summary_message(
    title: str,
    total: int,
) -> Dict:
    """构建摘要消息（第一条消息）"""
    date_str = datetime.now().strftime('%Y年%m月%d日')
    
    markdown_content = (
        f"# {title}\n\n"
        f"ฅʕ•̫͡•ʔฅ ◔.̮◔✧ (•̀ᴗ• ) ArXiv 小助手来啦！\n\n"
        f"📅 **日期:** {date_str}\n"
        f"📚 **找到论文:** {total} 篇\n\n"
        f"接下来将逐条推送每篇论文的详细信息..."
    )
    
    return {
        "msgtype": "markdown",
        "markdown": {
            "content": markdown_content
        }
    }


def post_to_wechat(webhook_url: str, payload: Dict) -> None:
    """发送消息到企业微信Webhook"""
    headers = {"Content-Type": "application/json"}
    response = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
    
    if response.status_code != 200:
        raise RuntimeError(
            f"企业微信Webhook请求失败: HTTP {response.status_code} {response.text}"
        )
    
    # 企业微信返回格式: {"errcode": 0, "errmsg": "ok"}
    try:
        result = response.json()
        if result.get("errcode") != 0:
            raise RuntimeError(
                f"企业微信Webhook返回错误: errcode={result.get('errcode')}, errmsg={result.get('errmsg')}"
            )
    except ValueError:
        # 如果响应不是JSON，使用原始文本
        raise RuntimeError(
            f"企业微信Webhook返回非JSON格式: {response.text}"
        )


def post_papers_separately(
    webhook_url: str,
    title: str,
    papers: List[Dict[str, str]],
    delay_seconds: float = 0.5,
) -> None:
    """将论文分成多条消息推送，每条消息一篇论文
    
    Args:
        webhook_url: 企业微信Webhook URL
        title: 消息标题
        papers: 论文列表
        delay_seconds: 每条消息之间的延迟（秒），避免发送过快
    """
    import time
    
    total = len(papers)
    
    if total == 0:
        # 如果没有论文，发送一条提示消息
        payload = build_summary_message(title, 0)
        post_to_wechat(webhook_url, payload)
        print("Sent summary message (no papers) to WeChat Work webhook.")
        return
    
    # 发送摘要消息
    summary_payload = build_summary_message(title, total)
    post_to_wechat(webhook_url, summary_payload)
    print(f"Sent summary message to WeChat Work webhook. Total papers: {total}")
    
    # 等待一下再发送论文详情
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    
    # 逐条发送每篇论文
    for idx, paper in enumerate(papers, 1):
        try:
            payload = build_single_paper_message(idx, total, paper, title)
            post_to_wechat(webhook_url, payload)
            print(f"Sent paper {idx}/{total} to WeChat Work webhook.")
            
            # 在消息之间添加延迟，避免发送过快
            if idx < total and delay_seconds > 0:
                time.sleep(delay_seconds)
        except Exception as e:
            print(f"Failed to send paper {idx}/{total}: {e}")
            # 继续发送其他论文，不中断整个流程
            continue
    
    print(f"Finished sending all {total} papers to WeChat Work webhook.")
