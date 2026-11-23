# Sprint2 后端提交历史补记

2026-11-24

## 背景

`backend_sprint2`（`f3932c3`）的 Sprint2 后端代码此前以压缩包方式复制到前端分支，并在 `3dda866` 中作为普通文件变更提交。因此 main 虽已包含对应的后端内容，但 `backend_sprint2` 的 12 个提交不在 main 的祖先链中，`git log main` 看不到这些提交记录。

## 处理

在 main 上新增一个以 `backend_sprint2` 为第二父提交的合并记录：

```text
git merge -s ours --no-ff backend_sprint2
```

该合并只补记祖先关系，文件树保持合并前的 main 不变。Sprint2 后端代码内容已在 `3dda866` 中完整整合，Sprint3 的后续改动不受影响。

## 验证

```bash
git merge-base --is-ancestor backend_sprint2 main   # 返回 0
git rev-list --count main..backend_sprint2          # 0
git rev-parse main^{tree}                            # 与合并前一致
```
