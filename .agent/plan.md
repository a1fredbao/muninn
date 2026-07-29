# Muninn - 架构设计与项目规划

## 1. 核心设计理念：宿主与插件架构

本项目旨在将“背诵软件”解耦为一个 **“宿主容器 (Host)”** 和若干 **“背诵包插件 (Plugins)”**。

- **宿主 (CLI Framework)**：负责题目的调度算法（如按权重出题）、界面渲染、用户输入捕获、题库包的管理（导入/导出）以及进度的持久化存储。
- **插件 (Recite Pack)**：负责定义具体的题目逻辑，包含静态数据（如元素周期表、古诗文内容）和出题/判题的 Python 脚本。

这种架构能让用户自由开发、导入和导出第三方题库包，极大地提高了可扩展性。

---

## 2. “背诵包”的规范定义 (Package Specification)

一个标准的背诵包在物理上是一个独立的文件夹，分发时可打包为 `.zip`，结构如下：

```text
chemistry/
├── manifest.json      # 包的元数据 (包名、包ID、作者、版本、描述、当前版本哈希)
├── data.csv           # 静态数据 (也可以是 json, yaml, sqlite 或媒体资源)
└── plugin.py          # 核心逻辑脚本 (必须实现 CLI 规定的标准接口)
```

---

## 3. 标准化 API 契约 (Plugin API Contract)

所有导入的 `plugin.py` 必须提供一个继承自 `BaseRecitePlugin` 的主类。CLI 会在初始化时将专用的工作区路径 (`workspace_dir`) 传给该插件，插件需从该路径加载自己的静态数据。

```python
class BaseRecitePlugin:
    def __init__(self, workspace_dir: str):
        """
        初始化插件
        :param workspace_dir: CLI 分配给该包的私有静态数据目录
        """
        self.workspace_dir = workspace_dir
        self.load_data()

    def load_data(self):
        """加载 workspace_dir 中的静态数据，由子类实现"""
        pass

    def get_all_problem_ids(self) -> list[str]:
        """返回题库中所有题目的唯一 ID，供 CLI 调度器建立索引和存档进度"""
        raise NotImplementedError

    def render_statement(self, problem_id: str) -> str:
        """根据题目 ID 返回要在终端显示的问题文本"""
        raise NotImplementedError

    def check_answer(self, problem_id: str, user_input: str) -> bool:
        """回调函数：判断用户输入是否正确"""
        raise NotImplementedError

    def get_expected_display(self, problem_id: str) -> str:
        """回答错误时，展示给用户的标准答案"""
        raise NotImplementedError

    def get_expand_info(self, problem_id: str) -> str:
        """回答正确时，展示给用户的拓展/提示信息 (可选)"""
        return ""
```

---

## 4. CLI 宿主的四大职责 (CLI Core Responsibilities)

1. **包管理器 (Package Manager)**
   - `new`: 在当前工作目录生成一个标准的背诵包插件模板（包含 `manifest.json`, 示例 `plugin.py` 和数据文件），方便用户快速开始自己的开发。
   - `import`: 接收一个本地的文件夹路径或 `.zip` 压缩包，将其拷贝/解压至 `~/.muninn/packs/<pack_id>/`，并校验完整性。如果本地已经有该包的旧版本，应该覆盖为新版本。
   - `loader`: 使用 `importlib` 动态加载包内的 `plugin.py`。
2. **状态与存储管理器 (State Manager)**
   - **进度隔离**：进度的存储（答对次数、耗时）绝对不能放在包的 `workspace_dir` 中，以防止导出时泄露私人数据。
   - 所有进度集中存放在 `~/.muninn/states/<pack_id>.db`。
3. **全局调度算法 (Global Scheduler)**
   - 提取自当前的智能权重逻辑。接管出题顺序，在内存中维护优先队列。
4. **统一终端 UI (Terminal UI)**
   - 负责 ANSI 颜色输出、清屏操作、数据统计的 banner 显示及捕捉用户输入。

---

## 5. 工作流示例 (Workflow)

当用户运行命令 `muninn run my_chemistry_pack` 时：

1. **CLI 启动**：定位到 `~/.muninn/packs/my_chemistry_pack/`。
2. **实例化插件**：初始化插件并传入 `workspace_dir`，插件完成数据加载。
3. **初始化调度**：CLI 调用 `get_all_problem_ids()`，并从 State Manager 读取每个题目的权重，压入堆中。
4. **游戏循环**：
   - 调度器弹出一道题的 ID。
   - CLI 调用 `render_statement(ID)` 打印题目。
   - CLI 截获用户输入 `user_input`。
   - CLI 将其传给插件：`check_answer(ID, user_input)`。
   - 得到 True/False 后，CLI 更新权重并保存状态，打印拓展信息或标准答案。
   - 循环往复。

---

## 6. 项目系统目录架构

```text
muninn/                       # 源码库目录
├── src/                      # 核心源码
│   ├── core/
│   │   ├── base_plugin.py    # 插件基类 API 契约
│   │   ├── scheduler.py      # 权重与出题队列调度算法
│   │   └── state.py          # 学习进度持久化管理
│   ├── cli/
│   │   ├── manager.py        # New/Import 包管理模块
│   │   └── runner.py         # 核心游戏循环 (整合 UI, Plugin, Scheduler)
│   └── ui.py                 # 终端渲染与颜色控制
└── pyproject.toml        # 使用 uv 管理依赖，打包配置，注册全局命令 'muninn'

~/.muninn/                # App Data 目录 (程序运行时在用户系统生成)
├── packs/                # 统一存放通过 import 导入的第三方题库包
│   └── chemistry/        # 具体的包目录 (被当作 workspace_dir)
│       ├── manifest.json
│       ├── data.csv
│       └── plugin.py
└── states/               # 进度隔离存储
    └── chemistry.db      # 记录该题库中所有题目的熟练度和学习数据
```
