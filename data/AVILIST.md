# 全球鸟类名录

`checklist.json` 收录 AviList v2026 中标为 `species` 的全部 11,172 条记录，涵盖 45 目、250 科和 2,379 属。文件保留原始分类顺序，包含来源收录的已灭绝物种。版本发布日期为 2026 年 10 月 20 日。[正式版本](https://www.avilist.org/checklist/v2026/) · [来源下载](https://explore.avilist.org/data/avilist-2026.json)

来源署名为 AviList Core Team. 2026. *AviList: The Global Avian Checklist, v2026.* 本站依照 CC BY 4.0 选取物种行和部分字段，修改字段名，并从学名提取属名。英文分布和灭绝标注保留来源原文。[引用标识 DOI](https://doi.org/10.2173/avilist.v2026) · [CC BY 4.0 许可](https://creativecommons.org/licenses/by/4.0/)

## 字段对应

下表中的列号从 0 开始，适用于本次固定版本的 Explorer 数据。字段释义可在 AviList 官方版本页面的元数据文件中查看。

| 索引字段 | 来源列 | 含义 |
| --- | --- | --- |
| `id` | 19，Avibase ID | 来源提供的分类概念标识，例如 `avibase-40329BB6`。名称或排序变化时按标识关联。若物种拆分或归并，需复核分类概念和既有照片。 |
| `en` | 8，English Name: AviList | AviList 英文名 |
| `latin` | 5，Scientific Name | 学名 |
| `order`、`family` | 2、3 | 目、科的拉丁名 |
| `genus` | 5 | 从物种学名的第一个单词提取属名 |
| `range` | 13，Range | 来源中的英文分布说明 |
| `extinction` | 14，Extinction Status | 204 种有相关标注，下分已灭绝、可能灭绝、野外灭绝及重新引入等情形。字段缺失表示来源未给出这项标注。 |

## 复现

需要 Python 3.8 或更高版本。在仓库根目录运行 `python scripts/import_checklist.py`。脚本下载约 21 MB 的官方版本文件，核验 SHA-256、编号、学名和物种数后，原子替换索引。已有下载副本时可运行 `python scripts/import_checklist.py --input path/to/avilist-2026.json`。

本次原始文件 SHA-256 为 `0f00995c819903e35eaee65cf5313193868362f1a6383e05949fe3d3600a8b39`。采用新版本或上游更正文件时，先核对列定义、物种数和分类变动，再更新导入参数及来源说明。

## 目和科的英文名

`taxon-labels-en.json` 收录 AviList v2026 英文名委员会核定的全部 45 个目名和 250 个科名。数据来自同一份 CC BY 4.0 名录，选择第 1 列标为 `order` 或 `family` 的行，将第 5 列的学名对应到第 8 列的 AviList 英文名，保留官方拼写及排列顺序。每个物种的目和科都能在这两组名称中查到。[版本说明与署名](https://www.avilist.org/checklist/v2026/)

在仓库根目录运行 `python scripts/import_english_taxa.py`。也可用 `--input path/to/avilist-2026.json` 从已下载的原始快照重建。脚本复用主名录的 SHA-256 校验，并对照所有物种行核验分类覆盖。
