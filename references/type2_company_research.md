# Type 2: Company Research Pipeline

Detailed guide for conducting company research. Covers Tech companies (Part 1) and Finance companies (Part 2).

## Sub-Type Classification

| Sub-Type | Trigger Keywords | Template |
|----------|-----------------|----------|
| **Tech Company** | AI, SaaS, 互联网, 硬件, 软件, 芯片, cloud | `company_research_tech.md` |
| **Finance Company** | 银行, 保险, 支付, 牌照, 合规, 信贷, 资管 | `company_research_finance.md` |

## Pipeline: Tech Company

### Search Keyword Generation (9 Chapters)

| Chapter | Search Queries |
|---------|---------------|
| 1. Company Overview | `"[company]" founded headquarters employees revenue overview` |
| 2. History | `"[company]" history timeline milestones funding rounds IPO` |
| 3. Management | `"[company]" CEO founder CTO management team background` |
| 4. Products | `"[company]" products services pricing features comparison` |
| 5. Customers | `"[company]" customers users market geographic revenue breakdown` |
| 6. Industry | `"[industry]" market size CAGR forecast regulation trends` |
| 7. Competition | `"[company]" competitors market share landscape comparison` |
| 8. TAM | `"[industry]" TAM SAM SOM addressable market opportunity` |
| 9. Risks | `"[company]" risks challenges regulatory compliance threat` |

### Key Data Fields
- Financial: revenue, gross margin, net income (3-year trend)
- Capital structure: IPO details, valuation, major shareholders
- Product matrix: consumer products vs enterprise products
- Customer metrics: total users, enterprise clients, geographic split
- Industry: market size, CAGR, regulatory framework
- Competition: comparative table of 3-5 major competitors

### Search Strategy
1. Company SEC filings / annual reports → for financial data
2. Crunchbase / PitchBook → for funding history
3. News articles → for recent developments
4. Company blog / press releases → for product launches
5. Industry reports (Gartner, IDC) → quoted in news

---

## Pipeline: Finance Company

### Search Keyword Generation (12 Chapters)

| Chapter | Search Queries |
|---------|---------------|
| 1. Success Factors | `"[company]" success competitive advantage why growth` |
| 2. Basic Info | `"[company]" founded headquarters employees team structure` |
| 3. Funding | `"[company]" funding rounds investors valuation IPO` |
| 4. Founders | `"[CEO name]" background career experience previous company` |
| 5. Users & Market | `"[company]" users market region country user growth demographics` |
| 6. Compliance | `"[company]" license compliance regulation authorized KYC AML` |
| 7. Products | `"[company]" products services card payment wallet lending` |
| 8. Partners | `"[company]" partners Visa Mastercard bank custody KYC provider` |
| 9. Pricing | `"[company]" fees pricing commission subscription charges` |
| 10. Growth | `"[company]" user acquisition growth referral KOL marketing` |
| 11. Business Model | `"[company]" revenue business model TPV transaction volume` |
| 12. Risks | `"[company]" risks regulatory compliance market competition` |

### Special: License Verification
For finance companies, license data is critical. Search strategy:
1. Search `site:[regulator_site] "[company name]"` to verify licenses
2. Cross-reference with `config/policy_sources.json` for regulator sites
3. Always include the regulator's public register URL as source

### Key Data Fields (Finance-specific)
- License types and jurisdictions
- User scale and geographic distribution
- Product matrix (C-end vs B-end)
- Partner ecosystem (issuing banks, KYC providers, custody)
- Fee structure (transaction fees, subscription, spreads)
- Growth strategy (referral tiers, incentive system)
- Revenue breakdown
- Compliance risks

---

## Report Generation

Read the appropriate template:
```python
from utils import read_template
# For tech companies
template = read_template("company_research_tech.md")
# For finance companies
template = read_template("company_research_finance.md")
```

Then call `llm_client.generate_report_section()` with template + data.
