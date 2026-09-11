# -*- coding: utf-8 -*-
"""命令行记账本 - 最小闭环版"""
import json
import os
from datetime import datetime

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")


def load_records():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        print("提示：data.json 读取失败，已按空数据处理。")
        return []


def save_records(records):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def input_amount():
    while True:
        raw = input("请输入金额（支持小数）：").strip()
        try:
            amount = float(raw)
        except ValueError:
            print("金额无效，请输入数字，例如 12.5")
            continue
        if amount <= 0:
            print("金额必须大于 0，请重新输入。")
            continue
        return amount


def add_record(records):
    amount = input_amount()
    category = input("请输入分类（直接回车为「未分类」）：").strip() or "未分类"
    note = input("请输入备注：").strip()
    records.append({
        "amount": amount,
        "category": category,
        "note": note,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    save_records(records)
    print("已记录一笔：%.2f 元，分类「%s」。\n" % (amount, category))


def view_records(records):
    if not records:
        print("还没有账目，先去记一笔吧。\n")
        return
    keyword = input("请输入要筛选的分类（直接回车显示全部）：").strip()
    if keyword:
        shown = [r for r in records if r.get("category") == keyword]
        if not shown:
            print("没有分类为「%s」的账目。" % keyword)
            return
    else:
        shown = records
    print("%-4s %-19s %-10s %-8s %s" % ("序号", "日期时间", "金额", "分类", "备注"))
    for i, r in enumerate(shown, 1):
        amount = float(r.get("amount", 0))
        # 当前记账只录入支出（正数），显示为 -；负数视为收入显示 +
        sign = "-" if amount >= 0 else "+"
        print("%-6d %-21s %-12s %-10s %s" % (
            i,
            r.get("time", ""),
            sign + format(abs(amount), ".2f"),
            r.get("category", "未分类"),
            r.get("note", ""),
        ))
    print("共 %d 条记录。\n" % len(shown))


def monthly_summary(records):
    default_month = datetime.now().strftime("%Y-%m")
    month = input("请输入年月（如 2026-09，直接回车为本月）：").strip() or default_month
    month_records = [r for r in records if str(r.get("time", ""))[:7] == month]
    if not month_records:
        print("「%s」还没有任何账目。" % month)
        return
    income = sum(-float(r["amount"]) for r in month_records if float(r.get("amount", 0)) < 0)
    expense = sum(float(r["amount"]) for r in month_records if float(r.get("amount", 0)) >= 0)
    print("===== %s 月度汇总 =====" % month)
    print("总收入：%.2f 元" % income)
    print("总支出：%.2f 元" % expense)
    print("结余：%.2f 元" % (income - expense))
    if expense > 0:
        print("----- 分类支出占比 -----")
        by_cat = {}
        for r in month_records:
            amount = float(r.get("amount", 0))
            if amount >= 0:
                cat = r.get("category", "未分类")
                by_cat[cat] = by_cat.get(cat, 0.0) + amount
        for cat, total in sorted(by_cat.items(), key=lambda x: x[1], reverse=True):
            print("%-10s %.2f 元（%.1f%%）" % (cat, total, total / expense * 100))
    print()


def main():
    records = load_records()
    print("欢迎使用记账本，当前已有 %d 条记录。" % len(records))
    while True:
        print("===== 菜单 =====")
        print("1 记一笔")
        print("2 查看流水")
        print("3 月度汇总")
        print("4 退出")
        choice = input("请选择：").strip()
        if choice == "1":
            add_record(records)
        elif choice == "2":
            view_records(records)
        elif choice == "3":
            monthly_summary(records)
        elif choice == "4":
            print("再见！")
            break
        else:
            print("无效选项，请输入 1、2、3 或 4。\n")


if __name__ == "__main__":
    main()
