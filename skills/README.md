# 个人使用的 Skills

## squeeze
grill-me 的反向。用于让 AI 渐进式回答你的问题，逐步深入获取你需要的答案。

## squeeze-with-docs
squeeze 的文档版。沿用先概览、再逐层深入的拆解方式，由 AI 自动回答各分支并生成带链接的层级 Markdown 文档，适合 token 充足、希望一次生成后按兴趣阅读的场景。

- 显式调用：`$squeeze-with-docs <你的问题>`。
- 默认入口：`docs/squeeze/<topic>/README.md`，也可指定输出路径、范围和深度。
- 每页先给当前层答案，再链接到子问题；提供返回总览、返回上级和相关问题导航。
- 具体问题直接回答；有意义的分支才单独成页，不为增加层数而拆分。

技能定义见 [squeeze-with-docs/SKILL.md](squeeze-with-docs/SKILL.md)。
