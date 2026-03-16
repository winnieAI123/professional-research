# Type 1: Product Research Pipeline

Detailed guide for conducting product research across three sub-types: Hardware, Software, and Service.

## Sub-Type Classification

After SKILL.md routes to this reference, determine the product sub-type:

| Sub-Type | Trigger Keywords | Template |
|----------|-----------------|----------|
| **Hardware** | 机器人, 设备, 终端, 硬件, 穿戴, IoT, sensor | `product_research_hardware.md` |
| **Software** | App, 平台, SaaS, 工具, 软件, 小程序 | `product_research_software.md` |
| **Service** | 保险, 贷款, 金融服务, 咨询, 订阅服务 | `product_research_service.md` |

## Pipeline: Hardware Product Research

### 🚨 Agent-Driven 逐章写作（MANDATORY）

硬件产品研究**禁止**使用 `run_report_gen.py` 一次性生成。必须逐章搜索 → 逐章写作 → 最终拼接。

### 执行流程

```
Phase 1: 模板解析
  ├── 读取 templates/product_research_hardware.md
  ├── 确定研究功能/特性 → 确定分析维度（3-6个）
  └── 初步搜索 → 识别品类分组

Phase 2: 逐章搜索+写作（8个章节）
  ├── 一、研究概述 ← 极少搜索，定范围
  ├── 二、品类与场景价值 ← 按品类搜索
  ├── 三、功能特征分析 ← 按维度搜索
  ├── 四、技术方案对比 ← 按品类+技术路线搜索
  ├── 五、产品详细扫描表 ← 逐品类逐产品搜索（最重）
  ├── 六、用户体验反馈 ← 搜用户评价
  ├── 七、商业化数据 ← 搜融资/定价/销量
  └── 八、Key Takeaways ← 不搜索，综合前7章（最后写，报告中放最前面，无编号）

Phase 3: 拼接 + Word 输出
  └── 报告顺序：Key Takeaways → 一 → 二 → 三 → 四 → 五 → 六 → 七 → 附录
```

### 各章节搜索关键词模板

#### 一、研究概述
- `"[品类名] market overview categories 2025"`
- `"[品类名] product landscape survey"`

#### 二、产品分类与场景价值
- `"[品类] [研究功能] application scenario use case"`
- `"[品类] [研究功能] value proposition benefit"`
- `"[品类] robot types categories overview"`

#### 三、功能特征分析

**维度确定方法**：Agent 根据研究功能自主确定维度。参考：
| 研究功能 | 推荐维度 |
|----------|---------|
| 跟随功能 | 跟随方向、速度范围、交互方式、适用环境、稳定性保障 |
| 睡眠管理 | 睡前功能、睡中监测、睡中干预、睡后分析 |
| 投影功能 | 投影技术、亮度/分辨率/画幅、交互方式、投影面适配 |
| 陪伴功能 | 情感表达、对话能力、记忆系统、主动交互 |

- `"[品类] [维度名] specifications comparison"`
- `"[产品名] [维度名] performance specs"`

#### 四、技术方案对比
- `"[品类] [功能] technology solution architecture"`
- `"[品类] sensor lidar camera UWB technical approach"`
- `"[产品名] technology patent technical specifications"`

#### 五、产品详细扫描表（最重章节）
- 按品类搜索：`"[品类] products list comparison 2025 2026"`
- 逐产品搜索：`"[产品名] [公司名] specifications features price"`
- 功能细节：`"[产品名] [研究功能] capabilities technology"`
- **每品类至少 3-5 个产品，重点品类 10+**

#### 六、用户体验反馈
- `"[产品名] user review experience rating"`
- `"[产品名] 用户评价 体验 口碑"`
- `"[品类] user feedback complaints issues"`

#### 七、商业化数据
- `"[公司名] funding valuation revenue 2025"`
- `"[产品名] price sales volume units shipped"`
- `"[公司名] 融资 估值 营收"`

#### 八、Key Takeaways
- **不搜索**。综合前 7 章写洞察总结。

#### 附录
- `"[品类] CES 2026 new products"`
- `"[品类] emerging startups innovations"`

### Data Sources
- `collect_search.py`: Tavily search with domains like techcrunch.com, theverge.com, cnet.com, 36kr.com
- `collect_search.py`: Tavily extract for product specification pages and full reviews

---

## Pipeline: Software Product Research

### Analysis Framework (15 Dimensions)

Generate search queries targeting each dimension:

#### 基础九维度
1. **Product Positioning**: `"[app name]" "what is" OR "product" core users scenario`
2. **Core Product Loop**: `"[app name]" features functionality "how it works"`
3. **Hook Mechanism**: `"[app name]" engagement addiction retention habit`
4. **Growth**: `"[app name]" user growth DAU MAU download "app store"`
5. **Retention**: `"[app name]" retention churn "user engagement" community`
6. **Monetization**: `"[app name]" revenue business model pricing subscription`
7. **Metrics**: `"[app name]" MAU DAU revenue ARR growth rate`
8. **Moat**: `"[app name]" competitive advantage moat network effect`
9. **Insight**: `"[app name]" future risk opportunity analysis`

#### 深度分析六维度（必填）
10. **Marketing Strategy**: `"[app name]" marketing campaign strategy CAC "customer acquisition cost"`
11. **Product Innovation**: `"[app name]" new features update "product update" changelog`
12. **User Insights**: `"[app name]" user reviews complaints feedback "app store review"`
13. **Monetization Deep Dive**: `"[app name]" subscription pricing "ad revenue" paywall`
14. **Industry Dynamics**: `"[app name]" funding investment "series A/B/C" valuation`
15. **Risk & Opportunity**: `"[app name]" privacy security regulation risk opportunity`

### 执行顺序

产品研究必须按以下顺序执行，共 **15 个维度全部覆盖**：

```
基础九维度（1-9）→ 深度六维度（10-15）→ 生成报告
```

**禁止跳过任何章节**。如某维度数据确实无法获取，必须标注"未找到相关公开数据（截至搜索日期）"并说明尝试过的搜索渠道。

### 推荐数据源

| 数据类型 | 推荐平台 |
|----------|----------|
| 用户数据 | QuestMobile、极光数据、Sensor Tower、七麦数据 |
| 财务数据 | 企查查、IT桔子、Crunchbase、上市公司财报 |
| 用户反馈 | App Store/Google Play 评论、微博、小红书 |
| 行业报告 | 36氪研究院、艾瑞咨询、QuestMobile报告 |
| 资本动态 | IT桔子、企名片、投资界、36氪融资快讯 |

### Data Standardization Fields
```json
{
  "product_name": "",
  "product_type": "social/AI/tool/content/game",
  "core_users": "",
  "main_scenarios": [],
  "key_differentiators": [],
  "core_features": [],
  "product_loop": "",
  "hook_mechanism": {"trigger": "", "action": "", "reward": "", "investment": ""},
  "growth_channels": [],
  "retention_sources": [],
  "monetization_model": "",
  "metrics": {"mau": "", "dau": "", "growth_rate": "", "retention_rate": "", "arr": ""},
  "moat": [],
  "source_urls": []
}
```

---

## Pipeline: Service Product Research

### Search Keyword Generation Strategy

From the service type, generate queries covering:

1. **Market overview**: `"[service type]" market size regional distribution China`
2. **Product structure**: `"[service type]" product comparison terms features benefits`
3. **Marketing tactics**: `"[service type]" marketing strategy online offline distribution`
4. **Competitive dynamics**: `"[service type]" competitor market share company product`
5. **Customer profile**: `"[service type]" customer demographics persona user segment`
6. **Regulatory environment**: `"[service type]" regulation compliance policy requirements`

### Data Standardization Fields
```json
{
  "service_name": "",
  "market_size": "",
  "regional_distribution": {},
  "customer_persona": "",
  "competitor_products": [],
  "product_terms_comparison": [],
  "effective_marketing": {"online": [], "offline": []},
  "competitive_dynamics": "",
  "regulatory_requirements": [],
  "source_urls": []
}
```

---

## Report Generation

After collecting data, read the appropriate template fresh:
```python
from utils import read_template
template = read_template("product_research_hardware.md")  # or software/service
```

Then call `llm_client.generate_report_section()` with the template and collected data. The template structure drives the report format — Gemini must follow it exactly.
