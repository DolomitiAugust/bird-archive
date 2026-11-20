# 中文维基百科原文补充

`scripts/import_accounts.py` 先从固定版本的 BirdNET+ 数据包生成物种简介。`scripts/import_wiki_accounts.py` 再检查其中仍使用英文原文的档案，寻找可核对的中文维基百科条目。

使用 [BirdNET+ Taxonomy v0.5-Nov2026](https://github.com/birdnet-team/birdnet-taxonomy/releases/tag/v0.5-Nov2026) 的 ZIP 文件，依次运行

```sh
python scripts/import_accounts.py --birdnet-zip BirdNET_Taxonomy_v0.5-Nov2026.zip
python scripts/import_wiki_accounts.py --birdnet-zip BirdNET_Taxonomy_v0.5-Nov2026.zip
```

两步均核对数据包的 SHA-256。第二步按 AviList 学名和 BirdNET+ 鸟种记录对应的 Wikidata QID 查找页面。同一 QID 对应多个目标种时跳过。已有中文条目链接的记录，优先核对页面 QID 和导言中完整的拉丁学名；可用 `--linked-only` 单独运行这一步。其他记录通过 Wikidata 查询，要求有物种分类阶元、中文维基百科站点链接，以及对应的学名或匹配的 Avibase 编号。有编号冲突的记录跳过。

脚本通过中文维基百科的 Action API 取得导言、页面属性和修订编号。只有维基项目编号与预期 QID 一致、属于文章命名空间且不是消歧义页时才使用导言。每条摘选不超过 3 个完整句子、440 字。条目当前没有可用导言时，保留原档案。脚本按批更新分片，原子替换单个文件。中断后可用相同命令继续，已补入的中文简介会被跳过。`--limit 160` 可先运行一小批。

直接取自中文维基百科的记录带 `via: "wiki"`、`qid`、`pageid` 和 `oldid`。其 `url` 指向实际读取的条目修订，以便逐条追溯。新运行从官方服务取得当时的数据，Wikidata 的分类、站点链接和百科条目修订会随时间变化。

中文原文归相应条目的维基百科贡献者，摘选、排版及展示遵循 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)。档案页提供原修订链接与许可说明。Wikidata 的关联资料使用 [CC0](https://www.wikidata.org/wiki/Wikidata:Licensing)。

也可以用短时批量查询补充缺少简介的档案。在仓库根目录运行以下命令，结果写成 `{物种编号: 中文简介}` 的独立文件，保留原分片。

```sh
python scripts/import_wiki_accounts.py --birdnet-zip BirdNET_Taxonomy_v0.5-Nov2026.zip --by-name-output data/zh-additions.part --seconds 150
python scripts/import_wiki_accounts.py --merge-supplement data/zh-additions.part
```

这一模式先查缺少任何简介的物种，再查只有英文简介的物种。每批最多查 20 个中文名，余下的尝试学名重定向，每个请求间隔至少半秒。页面的 QID 必须在名录中唯一且对应目标种。物种身份再通过两种方式之一核对：导言含完整接受学名，或 `chinese-names.json` 中已有通过 Wikidata 接受学名和物种阶元共同核对的同一 QID。可加 `--rank-verified-only` 只查后一组。达到时限、服务限流或网络异常时保留已取得的记录。再次运行同一输出文件会跳过已经收录的物种。
