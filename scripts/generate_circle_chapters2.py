# -*- coding: utf-8 -*-
"""Circle公司研究报告第7-12章生成脚本"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

from llm_client import generate_content

STYLE_INSTRUCTION = """
你是一位资深金融科技行业分析师。请以分析师视角撰写研究报告，严格遵守以下风格：

1. 像分析师写报告，不是填表：以叙述性分析为主，表格为辅。
2. 子标题必须有：每个章节下至少用2-4个###子标题划分内容块。
3. 关键发现开头：每章第一段用>引用块写1-2句核心结论。
4. 有限加粗：允许对关键数字和结论性判断加粗，每段最多1-2处。
5. 禁止空洞措辞：不要用"具有较大发展潜力"、"市场前景广阔"。
6. 自然引用来源：关键数据在正文中自然注明。
7. 反编造规则：没有数据就写"截至研究日期，该数据尚未公开披露"。
"""

def main():
    output_dir = "D:/clauderesult/claude0317"

    # 读取数据文件
    with open("data/circle_chapter7_12_data.txt", "r", encoding="utf-8") as f:
        data = f.read()

    prompt = f"""{STYLE_INSTRUCTION}

【任务】撰写Circle公司深度研究报告的第7章到第12章。

## 7. 产品矩阵

### 7.1 C端产品
[分析USDC和EURC作为C端稳定币产品的特点、定位和用户群体]

### 7.2 B端产品
[分析CPN、CCTP、USYC、Arc等产品矩阵，用表格呈现产品矩阵]

---

## 8. 合作伙伴生态

### 8.1 卡组织与Visa和 Mastercard）
[分析卡组织合作的重要性和战略意义]

### 8.2 交易所合作（Coinbase, Binance等）
[分析收入分成协议和战略价值]

### 8.3 资产管理合作（BlackRock）
[分析储备基金管理关系]

---

## 9. 定价策略

### 9.1 收入模式
[分析储备收入和分发成本的定价逻辑]

### 9.2 Developer Services定价
[分析免费层级和按量计费]

---

## 10. 增长策略

### 10.1 合作伙伴驱动
[分析分销激励机制]

### 10.2 合规先行
[分析合规战略对增长的推动]

---

## 11. 商业模式

### 11.1 收入结构
[用表格呈现营收构成]

### 11.2 成本结构
[分析分销成本和运营成本]

### 11.3 盈利能力
[分析净利润和调整后EBITDA]

---

## 12. 风险评估

### 12.1 合规与监管风险
[分析监管变化和牌照风险]

### 12.2 业务风险
[分析利率、竞争、储备风险]

### 12.3 市场风险
[分析脱锚、加密市场波动、技术风险]

---

【数据】
{data}
"""

    result = generate_content(prompt, max_output_tokens=6000)

    # 保存结果
    with open(f"{output_dir}/circle_chapter7_12.md", "w", encoding="utf-8") as f:
        f.write(result)

    print("第7-12章已保存到:", f"{output_dir}/circle_chapter7_12.md")
    print(result[:2000])

if __name__ == "__main__":
    main()
