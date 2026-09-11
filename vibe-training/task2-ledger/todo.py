# -*- coding: utf-8 -*-
"""命令行待办事项应用（单文件，无第三方依赖）"""
import json
import sys
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "todos.json"


def load_todos():
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_todos(todos):
    DATA_FILE.write_text(
        json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_index(args, todos):
    """解析并校验序号参数，返回 (index, 错误信息)"""
    if not args:
        return None, "请提供序号，例如：done 1"
    try:
        n = int(args[0])
    except ValueError:
        return None, f"无效的序号：{args[0]}"
    if not 1 <= n <= len(todos):
        return None, f"序号超出范围（当前共 {len(todos)} 条）"
    return n, None


def cmd_add(args, todos):
    if not args:
        print("用法：add <待办内容>，例如：add 买牛奶")
        return todos
    todos.append({"text": " ".join(args), "done": False})
    save_todos(todos)
    print(f"已添加：{todos[-1]['text']}")
    return todos


def cmd_list(_args, todos):
    if not todos:
        print("（暂无待办事项）")
        return todos
    for i, item in enumerate(todos, 1):
        mark = "x" if item["done"] else " "
        print(f"{i}. [{mark}] {item['text']}")
    return todos


def cmd_done(args, todos):
    n, err = parse_index(args, todos)
    if err:
        print(err)
        return todos
    todos[n - 1]["done"] = True
    save_todos(todos)
    print(f"已完成：{todos[n - 1]['text']}")
    return todos


def cmd_delete(args, todos):
    n, err = parse_index(args, todos)
    if err:
        print(err)
        return todos
    removed = todos.pop(n - 1)
    save_todos(todos)
    print(f"已删除：{removed['text']}")
    return todos


COMMANDS = {
    "add": cmd_add,
    "list": cmd_list,
    "done": cmd_done,
    "delete": cmd_delete,
}


def print_usage():
    print("未知命令。用法：")
    print("  add <内容>   添加待办，例如：add 买牛奶")
    print("  list         列出所有待办")
    print("  done <序号>  标记为已完成，例如：done 1")
    print("  delete <序号> 删除待办，例如：delete 1")


def main(argv):
    if not argv:
        print_usage()
        return 1
    cmd, *args = argv
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(f"未知命令：{cmd}")
        print_usage()
        return 1
    handler(args, load_todos())
    return 0


if __name__ == "__main__":
    code = main(sys.argv[1:])
    # 双击运行（无参数）时窗口会在打印后立即关闭，这里暂停一下
    if len(sys.argv) == 1:
        input("按回车键退出...")
    sys.exit(code)
