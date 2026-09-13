"""生成多学科查询集：每学科 10 个真实风格的查询 + gold 文档。

输出 bench/_queries_multi.json，检索评测脚本可指定 --queries-file 使用。
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).with_name("_queries_multi.json")

# 每条 (query, gold_doc_title, type)
# gold_doc_title 需与实际入库的 title 一致（即 .md 文件的 stem）
QUERIES = [
    # ── 计算机/软件/开发 (16 篇) ──
    ("Docker 容器化基础", "Docker 容器化基础", "title"),
    ("Docker 与虚拟机有什么区别", "Docker 容器化基础", "section"),
    ("Git 工作流 GitFlow 与 trunk-based", "Git 工作流", "section"),
    ("Kubernetes Pod 是什么", "Kubernetes 核心概念", "section"),
    ("Linux 常用命令 top/ps/grep", "Linux 常用命令", "section"),
    ("MySQL InnoDB 索引原理 B+ 树", "MySQL 索引原理", "section"),
    ("Redis 数据结构 string hash list set zset", "Redis 数据结构", "section"),
    ("RESTful API 设计原则", "RESTful API 设计", "section"),
    ("MySQL 事务隔离级别 脏读 不可重复读 幻读", "SQL 事务隔离级别", "section"),
    ("二叉树遍历 递归迭代", "二叉树遍历", "section"),
    ("动态规划入门 状态转移方程", "动态规划入门", "section"),
    ("哈希表原理 冲突解决", "哈希表原理", "section"),
    ("微服务拆分原则", "微服务拆分原则", "section"),
    ("排序算法 时间复杂度 对比", "排序算法对比", "section"),
    ("数据库三大范式", "数据库三大范式", "section"),
    ("数据库连接池 作用", "数据库连接池", "section"),

    # ── 测试 (6 篇) ──
    ("ISTQB 基础概念", "ISTQB 基础", "title"),
    ("Mock 与 Stub 的区别", "Mock 与 Stub", "title"),
    ("性能测试方法 负载 压力 容量", "性能测试方法", "section"),
    ("测试用例设计方法 等价类 边界值", "测试用例设计方法", "title"),
    ("测试金字塔 单元测试 服务测试 E2E", "测试金字塔", "section"),
    ("缺陷生命周期", "缺陷生命周期", "title"),

    # ── 产品 (5 篇) ──
    ("PRD 写作指南", "PRD 写作指南", "title"),
    ("KANO 模型 基本型 期望型 兴奋型", "需求优先级模型", "section"),
    ("RICE 评分 计算公式", "需求优先级模型", "section"),
    ("MVP 最小可行产品 设计", "MVP 设计", "title"),
    ("AB 测试 设计 流量分配", "AB 测试", "title"),
    ("用户画像 构建方法", "用户画像", "title"),

    # ── 经济学 (5 篇) ──
    ("GDP 国民收入 核算方法", "GDP 与国民经济", "title"),
    ("供给曲线 需求曲线 均衡价格", "供给曲线", "title"),
    ("货币政策 工具", "货币政策", "title"),
    ("通货膨胀 原因 影响", "通货膨胀", "title"),
    ("货币与银行 商业银行 央行", "货币与银行", "title"),

    # ── 英语 (4 篇) ──
    ("英语语法 时态", "英语语法时态", "section"),
    ("CET 4 6 词汇 备考", "CET 词汇备考", "title"),
    ("雅思写作 Task 2 评分标准", "雅思写作评分", "title"),
    ("英文商务邮件 格式", "英文商务邮件", "title"),

    # ── 法学 (4 篇) ──
    ("民法 物权 所有权", "民法物权", "title"),
    ("合同法 要约 承诺", "合同法基础", "title"),
    ("刑法 犯罪构成要件", "刑法基础", "title"),
    ("知识产权 著作权 专利", "知识产权基础", "title"),

    # ── 哲学 (4 篇) ──
    ("哲学入门 形而上学 认识论 伦理学", "哲学入门", "title"),
    ("苏格拉底 柏拉图 亚里士多德", "古希腊哲学", "title"),
    ("康德 三大批判", "德国古典哲学", "section"),
    ("逻辑学基础 命题 推理", "逻辑学基础", "title"),

    # ── 工业设计 (4 篇) ──
    ("工业设计史 包豪斯", "工业设计史", "section"),
    ("设计思维 empathize define ideate", "设计思维", "section"),
    ("人机工程学 座椅 高度", "人机工程学", "title"),
    ("材料工艺 注塑 CNC", "材料工艺", "title"),
]


def main() -> None:
    out = [{"q": q, "gold": gold, "type": t, "expected_doc_title": gold}
           for q, gold, t in QUERIES]
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已生成 {len(out)} 条查询 → {OUT.name}")
    # 按学科统计
    by_subj = {}
    for q, gold, _ in QUERIES:
        # 按 gold 文件名前缀分类
        for prefix, label in [("Docker", "cs"), ("Git", "cs"), ("Kubernetes", "cs"),
                               ("Linux", "cs"), ("MySQL", "cs"), ("Redis", "cs"),
                               ("RESTful", "cs"), ("SQL", "cs"), ("二叉树", "cs"),
                               ("动态规划", "cs"), ("哈希表", "cs"), ("微服务", "cs"),
                               ("排序", "cs"), ("范式", "cs"), ("连接池", "cs"),
                               ("ISTQB", "testing"), ("Mock", "testing"), ("性能测试", "testing"),
                               ("测试用例", "testing"), ("测试金字塔", "testing"), ("缺陷生命", "testing"),
                               ("PRD", "product"), ("需求优先级", "product"), ("MVP", "product"),
                               ("AB ", "product"), ("用户画像", "product"),
                               ("GDP", "economics"), ("供给", "economics"), ("货币", "economics"),
                               ("通胀", "economics"), ("货币与", "economics"),
                               ("英语", "english"), ("CET", "english"), ("雅思", "english"),
                               ("商务邮件", "english"),
                               ("民法", "law"), ("合同", "law"), ("刑法", "law"), ("知识产权", "law"),
                               ("哲学入门", "philosophy"), ("古希腊", "philosophy"),
                               ("康德", "philosophy"), ("逻辑学", "philosophy"),
                               ("工业设计", "industrial"), ("设计思维", "industrial"),
                               ("人机", "industrial"), ("材料", "industrial")]:
            if q.startswith(prefix) or gold.startswith(prefix):
                by_subj.setdefault(label, 0)
                by_subj[label] += 1
                break
    for s, n in sorted(by_subj.items()):
        print(f"  {s}: {n}")


if __name__ == "__main__":
    main()
