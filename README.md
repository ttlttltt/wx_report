# 微信 AI 新闻晨报

每天早上 8:00 抓取昨日 AI 新闻，生成中文摘要，并通过微信公众号测试号推送到你的微信。

## 方案边界

本项目使用微信公众号测试号推送，不使用个人微信机器人。个人微信自动化容易失效、被风控，长期维护成本不值得。

## 准备微信公众号测试号

1. 打开微信公众平台测试号：https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login
2. 用你的微信扫码关注测试号。
3. 记录测试号页面里的 `appID`、`appsecret`。
4. 在测试号页面找到你的微信号对应的 `openid`。
5. 新增模板，模板标题建议写：

```text
昨日 AI 新闻晨报
```

模板内容建议：

```text
{{first.DATA}}

日期：{{keyword1.DATA}}
类型：{{keyword2.DATA}}
摘要：{{keyword3.DATA}}

{{remark.DATA}}
```

6. 记录模板的 `template_id`。

## 本地试运行

PowerShell：

```powershell
$env:DRY_RUN="1"
$env:OPENAI_API_KEY="你的 OpenAI API Key"
python .\ai_news_push.py
```

`DRY_RUN=1` 会只打印摘要，不会推送微信。

如果你只是先测试抓新闻流程，可以暂时不要设置 `OPENAI_API_KEY`。注意：以 `wx...` 开头的是微信测试号 `appID`，不是 OpenAI API Key，不要填到 `OPENAI_API_KEY`。

真正推送前设置：

```powershell
$env:WECHAT_APP_ID="你的 appID"
$env:WECHAT_APP_SECRET="你的 appsecret"
$env:WECHAT_OPENID="你的 openid"
$env:WECHAT_TEMPLATE_ID="你的 template_id"
$env:OPENAI_API_KEY="你的 OpenAI API Key"
python .\ai_news_push.py
```

如果不设置 `OPENAI_API_KEY`，脚本会退化成标题列表，方便先验证微信推送链路。

## GitHub Actions 定时

把下面 secrets 配到仓库的 `Settings -> Secrets and variables -> Actions`：

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`
- `WECHAT_OPENID`
- `WECHAT_TEMPLATE_ID`
- `OPENAI_API_KEY`

工作流会在北京时间每天 08:00 执行。

## 可配置环境变量

- `OPENAI_MODEL`：默认 `gpt-4.1-mini`
- `OPENAI_BASE_URL`：默认 `https://api.openai.com/v1`，使用兼容 OpenAI 格式的中转站时改成对应地址，例如 `https://cca.maya.today/v1`
- `MAX_NEWS_ITEMS`：默认 `5`
- `NEWS_SOURCES_FILE`：默认 `news_sources.json`
- `LOCAL_TIMEZONE_HOURS`：默认 `8`
- `DRY_RUN`：设为 `1` 时不推送微信

如果你使用中转站，把中转站给你的 Key 填到 `OPENAI_API_KEY`，并在 GitHub 仓库的 `Settings -> Secrets and variables -> Actions -> Variables` 里新增：

```text
OPENAI_BASE_URL=https://cca.maya.today/v1
```

注意：中转站不是 OpenAI 官方服务，请自行评估稳定性、隐私和计费风险。

## 现实限制

微信公众号模板消息不适合塞很长的日报。默认控制在 5 条新闻，每条只保留标题和一句话影响判断。否则微信里阅读体验会很差。

## 新闻源策略

默认新闻源已经从 Google News 泛搜索改成高质量固定源，优先级是：

1. 官方发布：OpenAI、Google AI、NVIDIA AI
2. 开发者生态：Hugging Face
3. 深度分析：MIT Technology Review
4. 行业媒体：TechCrunch、VentureBeat
5. 中文补充：量子位

不要盲目堆新闻源。每天晨报的价值来自筛选，不来自抓得多。
