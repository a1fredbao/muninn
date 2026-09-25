# Muninn

Muninn (雾尼) - 高度可扩展的强化训练命令行工具。

[English](./README.md) &nbsp;|&nbsp;[完整文档](https://a1fredbao.github.io/muninn/)

## Muninn 是什么？

Muninn 是一个高度可扩展的命令行强化训练软件，名字取自北欧神话中代表"记忆"的乌鸦雾尼。它不包含任何硬编码的题目，而是采用了 **插件架构**。你可以安装别人编写的"训练包"（比如化学元素表、GRE 单词、历史事件），也可以自己使用 Python 开发训练包。

Muninn 作为"宿主"，为你提供了三大能力：

1. **智能出题调度算法**（根据历史正确率和耗时，专门盯着你的薄弱点出题）。
2. **状态与进度持久化**（你的每一次训练进度都会被保存下来，随时可以继续）。
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
# 从 GitHub 安装一个训练包
muninn install a1fredbao/muninn-chemistry-plugin

# 打开 Textual 训练库主页面
muninn

# 或直接进入指定训练包
muninn run muninn-chemistry-plugin
```

## 命令一览

| 命令                         | 说明                                                       |
| ---------------------------- | ---------------------------------------------------------- |
| `muninn`                     | 打开 Textual 训练库主页与插件管理界面。                    |
| `muninn install <source>`    | 安装训练包（本地目录、zip、GitHub URL 或 `user/repo`）。   |
| `muninn uninstall <pack_id>` | 卸载训练包。                                               |
| `muninn upgrade [pack_id]`   | 升级指定训练包或全部训练包。                               |
| `muninn list`                | 使用传统 CLI 列出已安装的训练包。                          |
| `muninn run <pack_id>`       | 直接进入指定训练包的 Textual 训练页面。                    |
| `muninn new <name>`          | 生成插件开发模板。                                         |

Textual 主页面快捷键：

| 按键      | 操作                     |
| --------- | ------------------------ |
| `Enter`   | 开始选中的训练包         |
| `i`       | 安装训练包               |
| `u`       | 升级选中的训练包         |
| `Shift+U` | 升级全部训练包           |
| `d`       | 卸载选中的训练包         |
| `r`       | 刷新 metadata            |
| `Ctrl+C`  | 退出应用                 |
| `Ctrl+P`  | 打开命令面板             |

答题时按 `Enter` 提交答案，按 `Ctrl+Enter` 换行。若终端会将 Command
修饰键传递给应用，`Command+Enter` 也可以换行。答案输入框会随内容自动
增高，达到训练页面可用高度的一半后改为内部滚动。

## 开发插件

完整文档请见：[a1fredbao.github.io/muninn](https://a1fredbao.github.io/muninn/)
