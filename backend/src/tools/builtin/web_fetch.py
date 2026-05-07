"""网页抓取工具 - 抓取网页内容并转换为 Markdown"""

import ipaddress
import os
import re
import socket
from typing import List, Dict, Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from hello_agents.tools import Tool, ToolParameter, ToolResponse, tool_action


# SSRF 防护：禁止访问的 IP 范围
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # 本地回环
    ipaddress.ip_network("10.0.0.0/8"),        # A 类私网
    ipaddress.ip_network("172.16.0.0/12"),     # B 类私网
    ipaddress.ip_network("192.168.0.0/16"),    # C 类私网
    ipaddress.ip_network("169.254.0.0/16"),    # 链路本地 / 云元数据
    ipaddress.ip_network("0.0.0.0/8"),         # 当前网络
    ipaddress.ip_network("::1/128"),           # IPv6 回环
    ipaddress.ip_network("fc00::/7"),          # IPv6 私网
    ipaddress.ip_network("fe80::/10"),         # IPv6 链路本地
]

_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "instance-data"}


class WebFetchTool(Tool):
    """网页抓取工具

    抓取网页内容并转换为 Markdown 格式。
    支持提取主要内容、清理无关元素。
    """

    def __init__(
        self,
        timeout: int = 15,
        max_content_size: int = 50000,
        user_agent: str = None,
    ):
        """初始化网页抓取工具

        Args:
            timeout: 请求超时时间（秒），默认 15
            max_content_size: 最大内容大小（字符），默认 50000
            user_agent: 自定义 User-Agent
        """
        super().__init__(
            name="web_fetch",
            description="抓取网页内容并转换为 Markdown 格式",
            expandable=True
        )

        self.timeout = timeout
        self.max_content_size = max_content_size
        self.user_agent = user_agent or "Mozilla/5.0 (compatible; TinyClawBot/1.0)"

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        """执行抓取（默认行为）"""
        url = parameters.get("url", "")
        return self._fetch(url)

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="url",
                type="string",
                description="要抓取的网页 URL",
                required=True
            ),
        ]

    def _fetch(self, url: str) -> ToolResponse:
        """抓取网页的核心实现

        Args:
            url: 网页 URL

        Returns:
            ToolResponse: 抓取结果
        """
        if not url:
            return ToolResponse.error(
                code="INVALID_INPUT",
                message="URL 不能为空"
            )

        # 验证 URL 格式
        if not url.startswith(("http://", "https://")):
            return ToolResponse.error(
                code="INVALID_URL",
                message="URL 必须以 http:// 或 https:// 开头"
            )

        # SSRF 防护：验证目标地址安全性
        ssrf_error = self._validate_url_security(url)
        if ssrf_error:
            return ToolResponse.error(
                code="SSRF_BLOCKED",
                message=ssrf_error
            )

        try:
            # 发送请求
            request = Request(url)
            request.add_header("User-Agent", self.user_agent)
            request.add_header("Accept", "text/html,application/xhtml+xml")
            request.add_header("Accept-Language", "zh-CN,zh,en;q=0.9")

            with urlopen(request, timeout=self.timeout) as response:
                # 检查内容类型
                content_type = response.headers.get("Content-Type", "")
                if not content_type.startswith("text/html"):
                    return ToolResponse.error(
                        code="UNSUPPORTED_CONTENT",
                        message=f"不支持的内容类型: {content_type}"
                    )

                # 读取内容
                html = response.read().decode("utf-8", errors="ignore")

            # 转换为 Markdown
            markdown = self._html_to_markdown(html)

            # 截断过长内容
            if len(markdown) > self.max_content_size:
                markdown = markdown[:self.max_content_size] + f"\n\n... (内容已截断，共 {len(markdown)} 字符)"

            return ToolResponse.success(
                text=markdown,
                data={
                    "url": url,
                    "content_length": len(markdown),
                    "truncated": len(markdown) >= self.max_content_size,
                }
            )

        except HTTPError as e:
            return ToolResponse.error(
                code="HTTP_ERROR",
                message=f"抓取失败 (HTTP {e.code}): {e.reason}"
            )
        except URLError as e:
            return ToolResponse.error(
                code="NETWORK_ERROR",
                message=f"网络错误: {str(e)}"
            )
        except Exception as e:
            return ToolResponse.error(
                code="FETCH_ERROR",
                message=f"抓取失败: {str(e)}"
            )

    def _html_to_markdown(self, html: str) -> str:
        """将 HTML 转换为 Markdown

        简单的 HTML 到 Markdown 转换，提取主要内容。

        Args:
            html: HTML 内容

        Returns:
            Markdown 文本
        """
        # 移除 script 和 style 标签
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # 移除注释
        html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

        # 提取 title
        title = ""
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = self._clean_text(title_match.group(1))

        # 提取 body 内容（如果有）
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.IGNORECASE | re.DOTALL)
        if body_match:
            html = body_match.group(1)

        # 移除导航、侧边栏、页脚等
        for tag in ['nav', 'aside', 'footer', 'header']:
            html = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # 转换标题
        for i in range(6, 0, -1):
            html = re.sub(
                f'<h{i}[^>]*>(.*?)</h{i}>',
                lambda m: f"\n{'#' * i} {self._clean_text(m.group(1))}\n",
                html,
                flags=re.DOTALL | re.IGNORECASE
            )

        # 转换段落
        html = re.sub(r'<p[^>]*>(.*?)</p>', r'\n\1\n', html, flags=re.DOTALL | re.IGNORECASE)

        # 转换链接
        html = re.sub(
            r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
            r'[\2](\1)',
            html,
            flags=re.DOTALL | re.IGNORECASE
        )

        # 转换粗体
        html = re.sub(r'<(strong|b)[^>]*>(.*?)</\1>', r'**\2**', html, flags=re.DOTALL | re.IGNORECASE)

        # 转换斜体
        html = re.sub(r'<(em|i)[^>]*>(.*?)</\1>', r'*\2*', html, flags=re.DOTALL | re.IGNORECASE)

        # 转换代码块
        html = re.sub(r'<pre[^>]*><code[^>]*>(.*?)</code></pre>', r'\n```\n\1\n```\n', html, flags=re.DOTALL | re.IGNORECASE)

        # 转换行内代码
        html = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', html, flags=re.DOTALL | re.IGNORECASE)

        # 转换列表
        html = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<[ou]l[^>]*>(.*?)</[ou]l>', r'\n\1\n', html, flags=re.DOTALL | re.IGNORECASE)

        # 转换换行
        html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)

        # 移除所有剩余的 HTML 标签
        html = re.sub(r'<[^>]+>', '', html)

        # 清理文本
        markdown = self._clean_text(html)

        # 添加标题
        if title:
            markdown = f"# {title}\n\n{markdown}"

        # 清理多余空行
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)

        return markdown.strip()

    def _clean_text(self, text: str) -> str:
        """清理文本

        Args:
            text: 原始文本

        Returns:
            清理后的文本
        """
        # 解码 HTML 实体
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")

        # 移除多余的空白
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n[ \t]+', '\n', text)

        return text.strip()

    def _validate_url_security(self, url: str) -> str:
        """SSRF 防护：验证 URL 目标地址是否安全

        Args:
            url: 要验证的 URL

        Returns:
            错误信息（空字符串表示安全）
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
        except Exception:
            return "URL 格式无效"

        if not hostname:
            return "URL 缺少主机名"

        # 检查主机名黑名单
        if hostname.lower() in _BLOCKED_HOSTNAMES:
            return f"禁止访问主机: {hostname}"

        # 解析域名为 IP 地址
        try:
            addr_infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            return f"无法解析主机名: {hostname}"

        for family, _, _, _, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            for network in _BLOCKED_NETWORKS:
                if ip in network:
                    return f"禁止访问内网地址: {hostname} ({ip})"

        return ""

    @tool_action("fetch_url", "抓取网页内容")
    def _fetch_action(self, url: str) -> str:
        """抓取网页内容

        Args:
            url: 要抓取的网页 URL
        """
        response = self._fetch(url)
        return response.text
