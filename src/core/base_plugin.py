import os


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
