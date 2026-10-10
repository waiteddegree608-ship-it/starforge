# sf-md-footnote-check

一个离线的、无第三方依赖的 Python 命令行工具，用于在转换文档前审查
Markdown 脚注标签。它会扫描一个或多个 `.md` / `.markdown` 文件（或递归
扫描目录），报告三类容易出现的问题：重复定义、已定义但未被引用、被引用
但未定义。这是一个人工智能辅助的原型，并非来自任何现有项目，也没有既定的
采用者或社区。

## 快速开始

```sh
python cli.py notes.md        # 单文件人工可读报告
python cli.py docs/           # 递归扫描目录
python cli.py --json docs/    # 稳定的 JSON 输出
python cli.py --quiet docs/   # 仅返回退出码
python cli.py --demo          # 合成示例，无需输入
python cli.py --help          # 帮助
```

`--demo` 会在工作目录的临时区域内创建几个合成 Markdown 文件，用与真实文件
相同的逻辑扫描它们，打印报告和 JSON 视图后清理。它覆盖重复标签、未引用定义、
未定义引用以及代码块忽略等情况。

## 真实示例

若 `guide/intro.md` 引用了 `[^alpha]` 两次，并包含重复定义与未被引用的
`[^orphan]`，运行 `python cli.py guide/` 会给出按文件划分的报告和全局汇总，
进程以状态码 `1` 退出。使用 `--json` 会得到按文件路径为键的稳定对象，格式
参见 `example.json`。

## 退出码

| 代码 | 含义 |
| ---- | ---- |
| 0 | 无重复、无未定义引用、无未引用定义 |
| 1 | 发现至少一个问题 |
| 2 | 用法错误（无路径、路径不存在）或文件不可读 |

## 局限

- 这是启发式文本扫描器，不是完整的 Markdown 解析器；四空格缩进代码块、
  引用块和 HTML 块未被特殊处理。
- 仅识别 `[^label]` 约定，标签按去空格并小写进行归一化。
- 文件按 UTF-8 读取（接受 BOM），逐行流式处理；不支持自动修复或渲染。

## 环境要求

Python 3.10 或更高版本，仅使用标准库。测试：`python -m unittest discover -s .`，
请在测试目录中运行。

## 许可证

MIT。本项目为人工智能辅助原型，按“原样”提供，不作任何保证，也不承诺准确性、
流行度或关联关系。

## 参考链接

- Pandoc issue #1603 — https://github.com/jgm/pandoc/issues/1603
- Pandoc issue #11596 — https://github.com/jgm/pandoc/issues/11596
