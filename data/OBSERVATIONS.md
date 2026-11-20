# 馆藏摄影索引

`observations.json` 通过 Avibase 编号把 8,631 张照片关联到 AviList v2026 的 8,631 个物种。Adam Jackson 编制的 Avicommons 为 eBird/Clements 分类体系挑选鸟类图像并裁切。本项目使用其中能追溯到 iNaturalist 原照片的部分。[Avicommons 项目](https://github.com/rawcomposition/avicommons) · [采用的 2025 索引版本](https://github.com/rawcomposition/avicommons/blob/44305ddac3df99474e8f0fca33b23907ca35eedb/public/2025.json)

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

## 署名和许可

照片权利归各创作者所有。Avicommons 提供裁切、构图和缩放版本。每条记录保留作者、原照片链接、缩略图和 900 像素版地址、许可名称与许可链接。任何本地格式转换、裁切或缩放应在图片说明中注明。网站的代码许可不可替代单张照片的许可。[来源使用说明](https://github.com/rawcomposition/avicommons/blob/main/README.md) · [来源许可问答](https://github.com/rawcomposition/avicommons/blob/main/FAQ.md)

7,423 张采用含非商业条款的许可，分别为 CC BY-NC 7,301 张、CC BY-NC-SA 122 张。其余为 CC BY 733 张、CC BY-SA 181 张、CC0 294 张。各许可的具体版本和适用地域以记录为准。本馆按个人非商业用途展示。

索引保留 Avicommons 已明确给出的有效许可版本。仅给出 iNaturalist 短代码（如 `cc-by-nc`）时，按平台公开映射给出 CC 4.0 或 CC0 1.0；所有指向不存在的 CC0 版本（如“CC0 3.0”）的记录均留待重新查证。[iNaturalist 许可代码与链接](https://github.com/inaturalist/inaturalist/blob/965832c83ab93b7a277d3c4918f43b0ac3c7211d/app/models/shared/license_module.rb)

## 重新生成

在仓库根目录执行 `python scripts/import_observations.py`。脚本从官方仓库的固定提交和 AviList 官方 Explorer 各下载一份数据并核验散列值；运行期间不逐张请求照片、不逐页抓取观测。可使用 `--photos` 和 `--taxonomy` 传入相同版本的本地原始文件。照片索引 SHA-256 为 `3fce5e48eec0f9136c341dfc29752b970505ffe4a43c45af6c223acecee117de`。[名录来源与许可](AVILIST.md)
