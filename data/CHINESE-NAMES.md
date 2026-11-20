# 中文名索引

`chinese-names.json` 提供物种中文名及地区别名，键为 AviList 的学名。`orders` 和 `families` 提供带有明确分类阶元的中文目名及科名。不同地区对同一物种有不同称名，页面可把已收录的各称名指向同一份档案。

物种名称主要取自 **BirdNET Team，BirdNET+ Taxonomy v0.5-Nov2026**。使用的是其公开数据归档。该项目整合 AviList、eBird、iNaturalist、Wikidata 等来源。这里提取中文常用名并合并地区别名。整体索引按 CC BY-SA 4.0 再分发，许可范围限于名称数据。[来源与许可](https://birdnet.cornell.edu/taxonomy/about#license) · [归档版本](https://github.com/birdnet-team/birdnet-taxonomy/releases/tag/v0.5-Nov2026) · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

导入时先检查 BirdNET+ 的学名、鸟纲、物种阶元和可用的 Avibase 编号，再按中国大陆、简体中文、通用中文及其他中文地区的顺序选取展示名。保留不同写法供检索，过滤未翻译的拉丁名。

缺少中文名的物种以及目、科的名称再用 Wikidata 查询。查询比对拉丁名和阶元，物种也核对可用的 Avibase 编号。目名及科名分别要求以「目」和「科」结尾，防止混用属名、俗称或代表种。无法唯一对应的记录保留空缺。带有 `wikidata` 字段的记录可直接用其 Q 编号回查，原始标签由 Wikidata 贡献者以 CC0 提供。[Wikidata 授权](https://www.wikidata.org/wiki/Wikidata:Licensing)

IOC World Bird List v15.2（Gill、Donsker、Rasmussen 编，International Ornithologists Union 发布）提供另一组来自全球名录的中文名称。数据取自 GBIF 登记的原始 ColDP 包，按 CC BY 4.0 复用。两个名录中学名、命名人与年份、英文名和所含亚种学名集合都吻合时，才采用其中的中文名。已有展示名保持优先，新增名称进入别名。含 `ioc: true` 的记录至少有一个名称来自该包；原表未提供可直接采用的中文目名、科名。[发布资料与许可](https://doi.org/10.15468/anfqn6) · [IOC 名录 v15.2](https://doi.org/10.14344/IOC.ML.15.2)

缺少的目名、科名进一步查询 GBIF Backbone Taxonomy（GBIF Secretariat，CC BY 4.0）。只收录其公开接口中注明来自 Catalogue of Life 的中文通用名。核对已接受学名、完整拼写、鸟纲和对应阶元；带 `gbif` 字段的条目可在 GBIF 查到分类记录及其来源。[GBIF Backbone Taxonomy](https://doi.org/10.15468/39omei)

## 更新

先生成 `data/checklist.json`，再在项目根目录用 Python 3.9 或更新版本运行以下命令。

```sh
python scripts/import_chinese_names.py
```

可用 `--birdnet-zip`、`--ioc-zip` 和 `--avilist-json` 指定本地原始发布包或快照，程序会核验 SHA-256。Wikidata 和 GBIF 的补充标签来自官方接口，随源数据修订而变化。全部来源处理成功才替换输出文件。
