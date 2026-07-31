# Muninn

Muninn (雾尼) - 高度可扩展的背诵/记忆命令行工具。

[English](./README.md) &nbsp;|&nbsp;[完整文档](https://a1fredbao.github.io/muninn/)

## Muninn 是什么？

Muninn 是一个高度可扩展的命令行背诵软件，名字取自北欧神话中代表"记忆"的乌鸦雾尼。它不包含任何硬编码的题目，而是采用了 **插件架构**。你可以安装别人编写的"题库包"（比如化学元素表、GRE 单词、历史事件），也可以自己使用 Python 开发题库。

Muninn 作为"宿主"，为你提供了三大能力：

1. **智能出题调度算法**（根据历史正确率和耗时，专门盯着你的薄弱点出题）。
2. **状态与进度持久化**（你的每一次练习进度都会被保存下来，随时可以继续）。
3. 干净、无干扰的**终端 UI**。

## 安装与使用

使用 `uv`（推荐）或 `pip` 全局安装 Muninn：

```bash
# 使用 uv 安装 (推荐)
uv tool install muninn-cli

# 或者使用 pip 安装
pip install muninn-cli
```

## 快速开始

```bash
# 从 GitHub 安装一个题库包
muninn install a1fredbao/muninn-chemistry-plugin

# 开始背诵
muninn run muninn-chemistry-plugin
```

## 命令一览

| 命令                         |                                                          |
| ---------------------------- | -------------------------------------------------------- |
| `muninn install <source>`    | 安装题库包（本地目录、zip、GitHub URL 或 `user/repo`）。 |
| `muninn uninstall <pack_id>` | 卸载题库包。                                             |
| `muninn list`                | 列出已安装的题库包。                                     |
| `muninn run <pack_id>`       | 开始背诵。                                               |
| `muninn new <name>`          | 生成插件开发模板。                                       |

## 开发插件

完整文档请见：[a1fredbao.github.io/muninn](https://a1fredbao.github.io/muninn/)
