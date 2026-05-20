# 贡献指南

[English](./CONTRIBUTING.md)

## 开发环境准备

1. Fork 仓库并创建功能分支。
2. 安装依赖：

```bash
pip install -e .[dev]
```

3. 复制环境变量模板：

```bash
cp .env.example .env
```

## 测试

提交 Pull Request 前请先运行测试：

```bash
pytest
```

## PR 规范

1. 保持提交聚焦、原子化。
2. 行为变更必须补充或更新测试。
3. 当安装方式或对外行为变化时同步更新 `README.zh-CN.md` 与 `README.md`。
4. 严禁提交密钥，`.env` 必须保持未被跟踪。
