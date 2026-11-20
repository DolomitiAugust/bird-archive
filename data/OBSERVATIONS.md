# 馆藏摄影索引

`observations.json` 通过 Avibase 编号把 10,665 张不同的 iNaturalist 摄影作品关联到 AviList v2026 的 10,665 个物种。8,631 张取自 Adam Jackson 编制的 Avicommons，1,318 张来自 BirdNET+ Taxonomy 的 iNaturalist 摄影索引，716 张通过 iNaturalist 官方 API 核实。每张照片都有仓库内的 WebP 缩略图。[Avicommons 项目](https://github.com/rawcomposition/avicommons) · [采用的 Avicommons 索引版本](https://github.com/rawcomposition/avicommons/blob/44305ddac3df99474e8f0fca33b23907ca35eedb/public/2025.json) · [BirdNET+ 官方发布](https://birdnet.cornell.edu/taxonomy/download) · [iNaturalist API](https://api.inaturalist.org/v2/docs/)

## 物种与照片匹配

导入时同时核对来源的 eBird 物种代码、学名与 AviList v2026 的 Cornell Lab 代码、学名。照片编号和对应物种必须各自唯一。Avicommons 的 iNaturalist 图片键为原始照片的数字编号，其余来源使用哈希键。原始照片可由 `https://www.inaturalist.org/photos/{photoId}` 追溯。这个编号指向照片；同一观测可以有多张照片。[来源键生成规则](https://github.com/rawcomposition/avicommons/blob/44305ddac3df99474e8f0fca33b23907ca35eedb/pages/api/%5Bcode%5D/update.ts)

来源快照共 10,185 条。以下按表格顺序筛选，每条剔除记录只计一次。

| 剔除原因 | 条数 |
| --- | ---: |
| 非 iNaturalist 数字照片编号，原始媒介类型需要核对 | 1,080 |
| eBird 代码或学名与当前分类不完全一致 | 99 |
| 多个物种共用同一张照片 | 6 |
| 名录有需复核的灭绝标记 | 2 |
| 许可证的版本号无效 | 367 |

保留照片按来源精选与分类匹配收录。数据没有逐张提供野外拍摄环境或 iNaturalist 研究级观测等级，也无法证明每张照片均已由本馆人工鉴定。仿真标本、插画等混合来源留待人工核实。例如上游为 `Apteryx maxima` 选取的 Wikimedia 图像为历史绘画，未纳入本索引。[上游条目](https://avicommons.org/species/grskiw1)

第二组只处理第一组尚未覆盖的物种。对于 BirdNET+ Taxonomy v0.5-Nov2026，要求记录属于 Aves 的种级记录，Avibase 编号、学名均与 AviList 相同，来源明确为 iNaturalist，图片地址能指向其开放数据存储中的照片编号，且作者与可复用许可齐全。排除 758 条其他图源、245 条不合适或缺少明确定义的许可、51 条需复核的灭绝标注、3 条缺摄影者署名，以及 9 条存在跨种照片编号冲突的记录。入选图片沿用 iNaturalist 的 medium 和 large 尺寸，并保留原图页。[BirdNET+ 摄影字段说明](https://github.com/birdnet-team/birdnet-taxonomy/blob/v0.5-Nov2026/docs/metadata.md) · [iNaturalist 开放数据](https://github.com/inaturalist/inaturalist-open-data)

第三组在 2026 年 11 月 20 日通过 iNaturalist API 按剩余物种编号分批获取，保留逐张照片的作者、照片编号、许可和来源网址。689 条满足研究级观测、非圈养标志、当前有效物种与 AviList 学名精确一致，并且社区鉴定编号等于该种的 iNaturalist 编号。这些记录另附观测页。两条为 iNaturalist 物种照片目录直接确认了原图编号、物种、摄影者和 CC0 许可的记录。此批证据没有保存经纬度或具体观测位置。[核验快照](inaturalist-evidence.json)

最后一轮复核替换了 6 张来源失效的 BirdNET+ 图片，另补入 19 个物种。新增的 25 张中，22 张有研究级观测，3 张为当代圈养活体的观测。后者在详情单独标出。部分研究级记录使用来源认可的异名，或使用 AviList 确认归属该种的亚种名。保留原观测学名及观测链接。[复核记录](inaturalist-final-evidence.json)

摄影选集另收录 5 种灭绝鸟类的历史生前照片。每条附拍摄年代、馆藏或文件页，并说明野外或圈养背景。[选集照片档案](photos.json)

## 署名和许可

照片权利归各创作者所有。Avicommons 提供裁切、构图和缩放版本。每条记录保留作者、原照片链接、缩略图和较大尺寸图片的地址、许可名称与许可链接。任何本地格式转换、裁切或缩放应在图片说明中注明。网站的代码许可不可替代单张照片的许可。[来源使用说明](https://github.com/rawcomposition/avicommons/blob/main/README.md) · [来源许可问答](https://github.com/rawcomposition/avicommons/blob/main/FAQ.md)

8,927 张采用含非商业条款的许可，分别为 CC BY-NC 8,687 张、CC BY-NC-SA 240 张。其余为 CC BY 1,037 张、CC BY-SA 369 张、CC0 332 张。各许可的具体版本和适用地域以记录为准。本馆按个人非商业用途展示。

索引保留 Avicommons 已明确给出的有效许可版本。仅给出 iNaturalist 短代码（如 `cc-by-nc`）时，按平台公开映射给出 CC 4.0 或 CC0 1.0；所有指向不存在的 CC0 版本（如“CC0 3.0”）的记录均留待重新查证。[iNaturalist 许可代码与链接](https://github.com/inaturalist/inaturalist/blob/965832c83ab93b7a277d3c4918f43b0ac3c7211d/app/models/shared/license_module.rb)

BirdNET+ 来源的索引资料署名为 *BirdNET+ Taxonomy v0.5-Nov2026, https://birdnet.cornell.edu/taxonomy, CC BY-SA 4.0*。本站选取并规范化其中的摄影元数据、关联 AviList 编号，衍生的 BirdNET+ 元数据依照相同许可发布。原摄影作品各自保留记录所列许可。[元数据许可与第三方权利](https://github.com/birdnet-team/birdnet-taxonomy/blob/v0.5-Nov2026/LICENSE-DATA.md)

## 重新生成

在仓库根目录执行 `python scripts/import_observations.py`。脚本从 Avicommons、BirdNET+ Taxonomy 和 AviList 官方发布渠道各下载一份版本数据并核验散列值。可使用 `--photos`、`--birdnet` 和 `--taxonomy` 传入相同版本的本地原始文件，或使用 `--output` 生成候选索引。该步骤生成含上游图像地址的索引，发布时再运行网站的缩略图缓存流程添加本地地址。Avicommons 索引 SHA-256 为 `3fce5e48eec0f9136c341dfc29752b970505ffe4a43c45af6c223acecee117de`，BirdNET+ ZIP 为 `6fd24ab69532dcbffa6c53061e55118afe367f94ef06f100f1f386ca5d5421a1`。[名录来源与许可](AVILIST.md)

实际更新时先使用 `python scripts/import_observations.py --output data/base.part` 生成前两组，再运行 `python scripts/supplement_inaturalist.py --base data/base.part --output data/full.part` 使用已存快照复现第三组。要重新找照片，第二条命令另加 `--refresh --birdnet <版本ZIP> --photos <Avicommons索引>`。采集器串行请求，每次请求至少间隔 1.2 秒，支持有限次数重试；官方活数据会变化，核对新快照后再更新发布版本。

最后运行 `python scripts/supplement_inaturalist.py --base data/full.part --snapshot data/inaturalist-final-evidence.json --output data/final.part`，再执行 `python scripts/cache_observation_photos.py --index data/final.part`。确认缩略图全部就绪后，用生成文件更新 `data/observations.json`。`scripts/review_remaining_photos.py --help` 列出重新查找最后一批观测所需的参数。
