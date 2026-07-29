# Muninn

Muninn (雾尼) - 高度可扩展的背诵/记忆命令行工具

## Muninn 是什么？

Muninn 是一个高度可扩展的命令行背诵软件，名字取自北欧神话中代表“记忆”的乌鸦雾尼。它不包含任何硬编码的题目，而是采用了**“宿主-插件 (Host-Plugin)” 架构**。你可以自由导入别人编写的“题库包”（比如化学元素表、GRE 单词、古诗文等），也可以自己使用 Python 轻松开发题库。

Muninn 作为“宿主”，为你提供了开箱即用的三大能力：

1. **智能出题调度算法**（根据历史正确率和耗时，专门盯着你的薄弱点出题）。
2. **状态与进度持久化**（你的每一次练习进度都会被保存下来，随时可以继续）。
3. 干净优雅的**终端 UI**。

## 安装与使用

我们推荐使用 `uv` 来全局安装 Muninn：

```bash
# 使用 uv 安装 (推荐)
uv tool install muninn

# 或者使用 pip 安装
pip install muninn
```

基础命令：

```bash
# 查看所有已导入的题库包
muninn list

# 导入一个外部题库包 (支持本地文件夹或 .zip 压缩包)
muninn import path/to/pack_or_zip

# 运行指定的题库
muninn run <pack_id>

# 生成一个新的题库开发模板
muninn new <your_new_pack_id>
```

## 插件开发指南

为 Muninn 开发一个自己的题库极其简单：

1. **生成开发模板**：

   ```bash
   muninn new my_cool_pack
   ```

   这会在当前目录下生成一个 `my_cool_pack` 文件夹，里面包含 `manifest.json` 和 `plugin.py`。

2. **认识包结构**：
   - `manifest.json`: 题库包的元数据（包名、作者、版本）。
   - `plugin.py`: 你的核心出题和判题逻辑。必须包含一个继承自 `BaseRecitePlugin` 的 `Plugin` 类。

3. **实现核心接口**：
   在 `plugin.py` 中，你需要实现几个简单的回调函数。CLI 在加载插件时会提供 `self.workspace_dir`，你可以利用它来读取你放在包里的静态数据（如 `data.csv`, `data.json`）。

   - `get_all_problem_ids()`: 返回题库中所有题目的唯一 ID 列表。
   - `render_statement(problem_id)`: 给定题目 ID，返回要在屏幕上显示的问题文本。
   - `check_answer(problem_id, user_input)`: 判断用户的输入是否正确，返回 True/False。
   - `get_expected_display(problem_id)`: 当用户答错时，返回显示给用户的标准答案。
   - `get_expand_info(problem_id)` (可选): 当用户答对时，返回一些补充拓展信息。

4. **测试并安装**：
   当你写完逻辑后，直接使用 import 导入它即可开始你的背诵之旅：

   ```bash
   muninn import ./my_cool_pack
   muninn run my_cool_pack
   ```
