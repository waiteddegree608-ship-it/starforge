# sf-md-ref-inventory

一个离线命令行小工具，用于审计一组 Markdown、Quarto（`.qmd`）或纯文本文件中的**引用键（citation key）**与**交叉引用标签（label/anchor）**。它帮助作者在正式渲染之前，快速发现三类常见问题：同一标签被重复定义、`[text](#id)` 链接指向了不存在的标签、标签定义后从未被引用（以及 BibTeX 条目从未被引用）。

## 状态与来源

本项目是**由 AI 辅助生成的原型**，并非从成熟产品中抽取。它**没有既有的采用度**，不代表任何现有编辑器、出版系统或工具的官方立场，也无任何背书。它只是一个起点，请按自己的项目约定进行调整。工具**不承诺准确性或正确性**，输出仅作参考提示。

## 环境要求

- Python 3.10 或更高版本。
- 仅使用标准库（`argparse`、`re`、`json`、`pathlib`、`sys`），无第三方依赖，无网络访问。

## 快速开始

```bash
python cli.py --help
python cli.py --demo
python cli.py docs/
python cli.py --format json docs/
python cli.py --check-bib --bib references.bib docs/
python cli.py --format json --out report.json docs/
```

支持 `.md`、`.markdown`、`.qmd`、`.txt`；传入目录会递归搜索这些扩展名。

## 真实示例

给定 `intro.md`（含 `# Introduction {#sec-intro}`、`## Method {#sec-method}`、`@fig-arch`、`[@smith2020]`）与 `figures.md`（含 `::: {#fig-arch}`、重复的 `{#sec-intro}`、`{#fig-orphan}`），运行：

```bash
python cli.py --check-bib --bib references.bib .
```

工具会报告：`sec-intro` 被定义两次；`fig-orphan` 已定义但从未被引用；任何指向未定义标签的链接；以及引用了但 BibTeX 中不存在的键。每条结果都带有文件与行号，便于直接定位。

## 输出与退出码

JSON 输出包含 `files`、`labels_defined`、`duplicates`、`undefined_refs`、`unused_labels`、可选的 `bib`、`read_errors` 与 `summary`；文本模式按小节打印相同信息。排序是确定性的。

退出码：`0` 正常完成；`1` 文件不可读或非 UTF-8；`2` 用法错误（如未提供路径）。

## 局限

- 这是基于正则的**启发式扫描**，不是真正的 Markdown/Pandoc 解析器，复杂语法可能被误读。
- 仅支持 UTF-8，解码失败会报错。
- BibTeX 支持极简，只识别顶层 `@type{key,`，不处理 `@string`、宏与 `crossref`。
- 不解析 include、短代码生成的标识符。
- 除非指定 `--out`，否则不写任何文件；不访问网络。

## 测试

```bash
python -m unittest discover -s . -p "test_*.py"
```

## 许可证

基于 MIT 许可证发布。软件按“原样”提供，不附带任何形式的担保。

## 参考链接

- Pandoc 手册（引用与属性语法）：https://pandoc.org/MANUAL.html
- Quarto 交叉引用：https://quarto.org/docs/authoring/cross-references.html
- Quarto 引用与参考文献：https://quarto.org/docs/authoring/citations.html
- 相关上游问题追踪：https://github.com/quarto-dev/quarto-cli/issues/11040 与 https://github.com/quarto-dev/quarto-cli/issues/7157
