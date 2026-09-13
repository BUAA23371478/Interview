# Git 工作流

## 主流模型

### Git Flow
- 主分支：master / develop
- 功能分支：feature/*
- 发布分支：release/*
- 热修复：hotfix/*
- 适合：版本化发布的项目（库、桌面软件）

### GitHub Flow
- 主分支：main
- 功能分支：feature/*
- PR + code review + CI 通过后 merge
- 适合：持续部署的 SaaS

### Trunk Based
- 所有人在 main 上短分支（< 1 天）
- 强 feature flag
- 适合：成熟 CI/CD + 强测试文化

## 常用命令

```bash
git log --oneline --graph --all    # 可视化分支
git rebase -i HEAD~3               # 交互式 rebase 整理提交
git reflog                         # 找回「误删」的提交
git stash push -m "wip"            # 暂存未提交改动
git cherry-pick <commit>           # 挑选提交到当前分支
git bisect                         # 二分定位引入 bug 的提交
```

## 冲突解决

- rebase 冲突：`git rebase --continue` / `--abort`
- 工具：`git mergetool`（vimdiff / vscode / meld）
- 原则：先 rebase 本地，再 merge 远端

## 子模块与子树

### submodule
```bash
git submodule add <url> <path>
git submodule update --init --recursive
```
优点：独立版本管理；缺点：克隆需额外步骤。

### subtree
把外部仓库作为子目录，merge 时保留历史。
适合「想把外部代码一起管理」的场景。

## Hook 与 CI

- `pre-commit`：本地检查（格式化、Lint）
- `pre-push`：跑测试
- 服务端 hook：CI 流水线（GitHub Actions / GitLab CI）
