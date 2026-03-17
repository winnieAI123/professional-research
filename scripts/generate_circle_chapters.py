# -*- coding: utf-8 -*-
"""Circle公司研究报告逐章生成脚本 - 修复版"""
import sys
import os

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

from llm_client import generate_content

STYLE_INSTRUCTION = """
You是一位资深金融科技行业分析师。请以分析师视角撰写研究报告，严格遵守以下风格：

1. 像分析师写报告，不是填表：以叙述性分析为主，表格为辅。每个章节先用2-3段分析性文字阐述关键发现和判断。
2. 子标题必须有：每个章节下至少用2-4个###子标题划分内容块。
3. 关键发现开头：每章第一段用>引用块写1-2句核心结论。
4. 有限加粗：允许对关键数字和结论性判断加粗，每段最多1-2处。
5. 禁止空洞措辞：不要用"具有较大发展潜力"、"市场前景广阔"。所有判断必须有数据支撑。
6. 自然引用来源：关键数据在正文中自然注明。
7. 反编造规则：没有数据就写"截至研究日期，该数据尚未公开披露"。
"""

def main():
    output_dir = "D:/clauderesult/claude0317"

    # 第3-4章数据
    chapter3_4_data = """
融资历史:
- 2013年: 种子轮
- 2015年5月: Series A, IDG Capital等, 约500万美元
- 2018年5月: 1.1亿美元, Bitmain领投
- 2021年: Series F, 4亿美元, 多家VC
- 2021年: 计划SPAC上市(90亿美元估值), 未获SEC批准
- 2025年6月: IPO上市
  - IPO价格: 31美元
  - 筹资: 10.5亿美元
  - 上市估值: 80亿美元
  - 市值峰值: 420亿美元
- 2025年8月: 二次发行
  - 350万股, 130美元/股
  - 筹资: 4.55亿美元

主要投资者:
- General Catalyst (Jeremy Allaire曾担任EIR)
- Accel
- Greylock
- Kleiner Perkins
- Breyer Capital
- Digital Currency Group
- BlackRock (Fidelity管理Circle Reserve Fund)
- Fidelity
- ARK Invest
- IDG Capital

创始团队:
- Jeremy Allaire: CEO兼董事长
  - 1971年出生, 连续创业者
  - 创立Allaire Corp(ColdFusion)和Brightcove
  - 2013年创立Circle
- Sean Neville: 联合创始人
  - 技术背景
  - 仍担任董事
- Heath Tarbert: 总裁
  - 2020年加入
  - 前CFTC主席

用户规模:
- USDC覆盖: 5亿+钱包
- 覆盖: 185+国家
- 支持链: 30+
- USDC流通量: 753亿美元(2025年)
- EURC流通量: 9.2亿美元

合规牌照:
- 55+张全球牌照
- 关键牌照:
  - NYDFS BitLicense (2015年, 首家)
  - MiCA合规 (2024年, 首家)
  - OCC国家信托银行 (2025年, 有条件批准)
  - MAS牌照 (新加坡)
  - FCA牌照 (英国)
  - BMA牌照 (百慕大)
  - ADGM牌照 (阿布扎比)
"""

    prompt = f"""{STYLE_INSTRUCTION}

【任务】撰写Circle公司深度研究报告的第3章到第6章：

## 3. 融资历史

> Circle通过多轮融资和战略上市，建立了全球合规稳定币发行商的地位。

### 3.1 融资历程

[用叙述性文字介绍融资历程]

### 3.2 融资轮次表

| 轮次 | 时间 | 金额 | 领投/跟投 | 投后估值 |
|------|------|------|----------|--------------|
| 种子轮 | 2013年 | 约500万美元 | - | - |
| Series A | 2015年5月 | 约500万美元 | IDG Capital等 | - |
| Series B | 2018年5月 | 1.1亿美元 | Bitmain领投 | 约6亿美元 |
| Series F | 2021年 | 4亿美元 | 多家VC | 约7.7亿美元 |
| SPAC | 2021年 | 估值90亿美元 | Concord Acquisition | - | 未完成 |
| IPO | 2025年6月5日 | 10.5亿美元 | - | 80亿美元 |
| 二次发行 | 2025年8月 | 4.55亿美元 | - | - |

### 3.3 主要投资者

[分析主要投资方背景]

---

## 4. 创始团队

> Circle由连续创业者Jeremy Allaire和技术专家Sean Neville于2013年联合创立。

### 4.1 Jeremy Allaire (CEO兼董事长)

**背景**: 1971年出生, Macalester学院毕业
**职业经历**:
- 1995年: 与兄弟JJ Allaire共同创立Allaire Corp (ColdFusion开发平台)
- 1999年: Allaire Corp在纳斯达克IPO
- 2004年: 创立Brightcove (在线视频平台)
- 2012年: Brightcove在纳斯达克IPO
- 2013年: 创立Circle

**核心能力**: 战略愿景、 监管关系、 资本市场运作

### 4.2 Sean Neville (联合创始人)

**背景**: 技术专家
**角色**: 仍担任董事
**核心能力**: 技术架构设计

### 4.3 Heath Tarbert (总裁)

**背景**: 2020年加入, 前CFTC主席
**核心能力**: 监管合规、 法律背景

---

## 5. 用户与市场

### 5.1 市场规模

> USDC是全球第二大稳定币, 终端用户钱包达5亿+个, 覆盖185+国家.

**关键指标**:
- USDC流通量: 753亿美元 (2025年, 同比+72%)
- EURC流通量: 9.2亿美元 (同比+76%)
- 覆盖国家: 185+
- 终端钱包: 5亿+

### 5.2 用户画像

**B端机构客户**:
- 金融机构
- 支付公司(Visa, Mastercard)
- 特点: 需要合规、稳定、可审计

**C端零售用户**:
- 加密货币投资者
- 新兴市场用户
- 特点: 追求便利、低成本

---

## 6. 合规与牌照

### 6.1 合规战略

> Circle的合规优先战略是其核心竞争优势。公司选择了一条资本密集且监管严格的重资产合规路径。

**关键牌照**:
- NYDFS BitLicense (2015年, 首家)
- MiCA合规 (2024年, 首家全球稳定币发行方)
- OCC国家信托银行 (2025年, 有条件批准)
- MAS牌照 (新加坡)
- FCA牌照 (英国)
- BMA牌照 (百慕大)

**牌照总数**: 55+
"""

    result = generate_content(prompt, max_output_tokens=4000)

    # 保存结果
    with open(f"{output_dir}/circle_chapter3_6.md", "w", encoding="utf-8") as f:
        f.write(result)

    print("第3-6章已保存到:", f"{output_dir}/circle_chapter3_6.md")
    print(result[:2000])

if __name__ == "__main__":
    main()
