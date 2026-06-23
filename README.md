# AI 新闻晨报推送

每天北京时间 10:30 抓取昨日 AI 新闻，生成中文摘要，并通过 PushPlus 推送到微信。

## 推送通道

本项目已改为 PushPlus 推送，不再使用微信公众号测试号模板消息。测试号模板展示能力太弱，不适合日报阅读。

## PushPlus 准备

1. 登录 PushPlus。
2. 关注 PushPlus 的微信服务号。
3. 在 PushPlus 后台获取你的 token。
4. 到 GitHub 仓库配置：

```text
Settings -> Secrets and variables -> Actions -> Secrets
```

新增：

```text
PUSHPLUS_TOKEN=你的 PushPlus token
OPENAI_API_KEY=你的 AI 中转站或 OpenAI API Key
```

## GitHub Actions Variables

到：

```text
Settings -> Secrets and variables -> Actions -> Variables
```

配置：

```text
OPENAI_BASE_URL=https://cca.maya.today/v1
OPENAI_MODEL=gpt-5.5
MAX_NEWS_ITEMS=8
```

如果你开启了国内可访问的日报页面托管，可以配置：

```text
REPORT_BASE_URL=https://你的可访问域名
```

手机不能访问 GitHub Pages 时，不要使用 GitHub Pages 地址作为 `REPORT_BASE_URL`。

## 定时

不要使用 GitHub Actions 自带 `schedule`。它在这个仓库上已经多次没有触发，继续依赖它不可靠。

推荐使用 cron-job.org 免费定时触发 GitHub Actions。

### cron-job.org 配置

创建一个 cron job：

```text
URL: https://api.github.com/repos/ttlttltt/wx_report/actions/workflows/daily-ai-news.yml/dispatches
Method: POST
Schedule: 你想要的北京时间，例如每天 10:30
```

Headers：

```text
Authorization: Bearer 你的 GitHub Personal Access Token
Accept: application/vnd.github+json
Content-Type: application/json
X-GitHub-Api-Version: 2022-11-28
```

Body：

```json
{
  "ref": "main",
  "inputs": {
    "force": "false"
  }
}
```

GitHub Personal Access Token 需要有权限触发这个仓库的 Actions workflow。建议使用 fine-grained token，只授权 `ttlttltt/wx_report` 这个仓库。

workflow 仍然保留手动触发：

```text
Actions -> Daily AI News -> Run workflow
```

脚本内置了“当天只推一次”保护，cron-job.org 偶尔重复触发也不会重复推送。

如果你在 GitHub 页面手动 `Run workflow` 并想强制再推一次，把 `force` 改成 `true`。

## 本地试运行

PowerShell：

```powershell
$env:DRY_RUN="1"
python .\ai_news_push.py
```

真正推送需要：

```powershell
$env:PUSHPLUS_TOKEN="你的 PushPlus token"
$env:OPENAI_API_KEY="你的 AI API Key"
$env:OPENAI_BASE_URL="https://cca.maya.today/v1"
$env:OPENAI_MODEL="gpt-5.5"
python .\ai_news_push.py
```

## 内容策略

- 默认最多推送 8 条。
- 有几条高质量新闻就推几条，不强行凑满。
- PushPlus 使用 Markdown 推送。
- 每条新闻包含标题、1-2 句摘要、影响判断和原文链接。
- 新闻源优先官方发布、开发者生态和严肃分析，弱化转载和营销内容。

不要盲目堆新闻源。晨报的价值来自筛选，不来自抓得多。
