# 物种简介

中文模式使用 `accounts/`，英文模式另有 10,359 种的英文原文保存在 `accounts-en/`。两组都按 Avibase 编号的前两位十六进制字符分成 256 份，访客打开物种档案时读取对应分片。每个条目记录语言、摘录和来源网址。

基础摘录取自 *BirdNET+ Taxonomy v0.5-Nov2026* 中明确标为 `wikipedia`、且能够链接到相应语言维基条目的文字。导入程序将学名和可用的 Avibase 编号与 AviList 比对，优先选择中文，其次是英文。每项选取最多三句完整原文。上游标为机器生成或机器翻译的摘要不进入本索引。感谢各条目贡献者和 BirdNET Team；选取、缩短和重新编排的摘录按 CC BY-SA 4.0 发布。百科资料反映各来源条目的内容，站内分类与分布采用 AviList v2026。[BirdNET+ 发布页](https://birdnet.cornell.edu/taxonomy/download) · [数据授权](https://github.com/birdnet-team/birdnet-taxonomy/blob/v0.5-Nov2026/LICENSE-DATA.md) · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

直接取得的中文简介以 `via: "wiki"` 记录，链接到中文维基百科的固定修订。这些文字的来源和更新方式见[中文资料说明](WIKI-ACCOUNTS.md)。

在仓库根目录运行 `python scripts/import_accounts.py` 生成两组基础摘录。用 `--english-only` 只重建英文索引。若已有 BirdNET+ 的官方归档，可用 `--birdnet-zip` 指定本地文件。脚本会核验归档的 SHA-256。
