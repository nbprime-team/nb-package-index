# 包依赖与接口设计

> ⚠️ AI 生成 / 辅助创作：DeepSeek V4.1 Flash（未人工审查）

## 依赖图（目标形态）

```text
unifont-font-1.0   (kind=lib/asset，字模数据 + 取字形 API)
      └── render-text-1.0   (FreeType 裁剪 + HarfBuzz，文字排版)
              ├── tex-math-1.0      (LaTeX 解析/排版，依赖 font + render)
              │       └── markdown-1.0  (文档解析 + 分页，依赖 tex)
              └── nbcode-1.0        (编辑器，依赖 render；可选依赖终端)
terminal-0.2        (sh：provides=terminal，可被其他包调用)
filemanager-0.1     (provides=filemanager：list/read/write/open 接口)
```

`requires` 是**精确包名**（含版本），装载顺序由依赖决定；共享库在 `sys/` 只存一份。

## 接口约定

| 接口 | 提供者 | 方法 |
|---|---|---|
| 字体 | `unifont-font` | `uf_glyph(cp, size, out)`、`uf_advance()` |
| 文字渲染 | `render-text` | `rt_measure/rt_draw/rt_layout` |
| 数学排版 | `tex-math` | `tex_parse/tex_layout/tex_draw` |
| 文档 | `markdown` | `md_open/md_page/md_close` |
| 文件管理器 | `filemanager` | `fm_list/fm_read/fm_write/fm_open` |
| 终端 | `terminal` | `term_run(argv)`（nbCode 可调用） |

## 迁移步骤

1. 把 unifont（已在 `toolchain/sdk`）打成 `unifont-font-1.0`；
2. 把 FreeType/HarfBuzz 裁剪版打成 `render-text-1.0`；
3. primetex 的 LaTeX 引擎抽成 `tex-math-1.0`，`primetex` 变为它的示例壳；
4. `markdown` 依赖 `tex-math`；
5. `filemanager`、`terminal` 暴露接口后，其他包用 `requires` 引用。
