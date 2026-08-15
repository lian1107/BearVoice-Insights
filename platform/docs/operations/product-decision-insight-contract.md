# 产品决策洞察工作流机器契约

```json
{
  "contract": "minerva-skill-output/1",
  "skill": "professionalize-ai-work",
  "verification": "partial",
  "input_digest": {
    "quoted_numbers": [],
    "sensitive_present": false
  },
  "risk": {
    "domain": "safety",
    "named_human_owner": "产品线品质负责人"
  },
  "data_boundary": {
    "excluded_data": "未脱敏原声、明文客户标识、未授权经营数据和供应商密钥"
  },
  "refusal_rules": [
    "AI 不确认质量根因，不决定召回、停售或产品立项",
    "经营分母缺失时不输出金额损失、收益承诺或 ROI",
    "敏感数据未通过隐私门禁时阻断模型外发"
  ],
  "mode": "systemise",
  "target_tasks": [
    "定位最值得处理的产品问题及受影响维度",
    "把客户原声转成可追溯产品决策卡",
    "为产品和品质负责人准备验证与审批材料"
  ],
  "work_map": [
    {
      "step": "数据治理与分母核对",
      "classification": "rule-stable",
      "human_owner": "数据运营"
    },
    {
      "step": "多信号抽取与模式发现",
      "classification": "case-assisted",
      "human_owner": "模型审核员"
    },
    {
      "step": "根因、改进方向和验证计划",
      "classification": "case-assisted",
      "human_owner": "产品与品质负责人"
    },
    {
      "step": "立项、处置与结果确认",
      "classification": "human-judgment",
      "human_owner": "具名业务审批人"
    }
  ],
  "knowledge_map": [
    {
      "source": "脱敏客户原声及导入哈希",
      "version_or_date": "每个导入批次版本",
      "condition": "仅支持样本内描述与线索发现",
      "grade": "A"
    },
    {
      "source": "SKU、渠道、批次和版本字段",
      "version_or_date": "原始业务导出版本",
      "condition": "字段存在且映射经过确认",
      "grade": "A"
    },
    {
      "source": "项目规则基线和历史报告",
      "version_or_date": "2026-08-15",
      "condition": "仅用于回归和案例提示",
      "grade": "C"
    },
    {
      "source": "AI 生成的根因和产品方向",
      "version_or_date": "每个分析运行版本",
      "condition": "仅作为候选线索，不能作为证据来源",
      "grade": "D"
    }
  ],
  "rules": [
    {
      "rule": "所有占比必须显示去重原声分母和覆盖范围",
      "standard_kind": "categorical"
    },
    {
      "rule": "安全风险优先进入人工复核，但不自动决定召回",
      "standard_kind": "categorical"
    },
    {
      "rule": "根因只能表述为待验证假设并列出缺失数据",
      "standard_kind": "categorical"
    },
    {
      "rule": "成本、收益和 ROI 在经营分母接入前保持 TBD",
      "standard_kind": "categorical"
    },
    {
      "rule": "产品方向必须附带可执行验证计划并由责任人审批",
      "standard_kind": "case-based"
    }
  ],
  "output_spec": "多维覆盖摘要、问题模式、产品决策卡、证据等级、改进方向、验证计划、缺失数据、禁止结论和人工责任人",
  "refusal_and_escalation": [
    "召回、停售和安全定性升级产品线品质负责人",
    "技术可行性和产品立项升级产品与研发负责人",
    "金额损失、收益和 ROI 升级经营与财务负责人",
    "隐私或授权异常升级数据运营与系统管理员"
  ],
  "test_pack": [
    {
      "case_type": "normal",
      "result": "验证多维数据可生成可追溯决策卡"
    },
    {
      "case_type": "boundary",
      "result": "验证低声量安全问题仍优先复核且不自动召回"
    },
    {
      "case_type": "missing-information",
      "result": "验证缺少经营分母时 ROI 保持 TBD"
    },
    {
      "case_type": "conflicting-rule",
      "result": "验证不同批次或版本的冲突表现被分层保留"
    },
    {
      "case_type": "refusal",
      "result": "验证系统拒绝确认根因或替代人工作出高风险决定"
    }
  ],
  "update_owner": "产品负责人维护决策卡，品质负责人维护安全规则，数据运营维护字段与分母，模型审核员维护提示词与黄金样本",
  "first_worked_example": "养生壶路演基线用于展示安全问题优先复核和经营分母缺失时的条件式产品建议"
}
```
