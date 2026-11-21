# 鸟类档案馆

按真实摄影浏览鸟种，也可以按鸟名、学名或分类查阅全球名录。[打开档案馆](https://dolomitiaugust.github.io/bird-archive/)

首次访问默认中文和暗色。页首的语言菜单按「中文、English」排列。切换会保留当前档案、筛选条件和页码，语言与明暗偏好分别保存。也可直接打开[英文版](https://dolomitiaugust.github.io/bird-archive/?lang=en)。

封面照片可直接打开对应档案。图库左侧是分类目录，右侧的照片签列鸟名与学名，窄屏上简化为鸟名。打开档案可查分类、英文分布原文、已有简介、照片出处和使用许可。在全球名录中，可用中文名、地区别名、英文名或学名检索，也可按目、科或照片收录情况筛选。没有可靠照片的物种同样保留独立档案。[查看照片待补的物种](https://dolomitiaugust.github.io/bird-archive/#checklist?media=missing)

## 本地运行

在仓库根目录运行以下命令，然后打开浏览器访问本机的 8000 端口。

```sh
python -m http.server 8000
```

## 照片与署名

页首和扉页使用蓝脚鲣鸟实拍。点击扉页照片可打开该物种档案。

这是个人非商业档案馆。照片各自遵循其文件页的许可，包括只允许非商业使用的作品。选集和全球图库都保留摄影者、来源页、许可链接和图像处理说明。总览使用本地缩略图。点进物种档案，优先显示馆内保存的大图或摄影者上传的同一张原片。馆藏标本和历史影像单独标记。[摄影来源和筛选方式](data/OBSERVATIONS.md)

## 资料与维护

- 分类、分布和目科英文名采用 AviList v2026。[名录说明](data/AVILIST.md)
- 中文名、区域别名及目科名分别记录了来源和许可。[中文名索引](data/CHINESE-NAMES.md)
- 物种简介按档案加载，并保留语言和出处。[摘录说明](data/ACCOUNTS.md)
- 外部物种资料以已核实的编号关联 eBird、BirdLife、Birds of the World、iNaturalist 和 GBIF。[外部资料索引](data/references.json)

Python 3.10 及以上版本可运行维护脚本。照片下载和检查还需要 Pillow。以下命令适用于已经克隆的仓库。

```sh
python -m pip install Pillow
python scripts/sync_photos.py --verify-only
python scripts/apply_photo_review.py --verify-only
python scripts/check_archive.py --gaps data/gaps.csv --english-gaps data/gaps-en.csv
```

补充选集时，先在 `data/photos.json` 登记物种、原始照片页、摄影者和逐图许可，再运行 `python scripts/sync_photos.py`。更新全球图库时按摄影索引的说明合并来源快照，再缓存缩略图。已有图片经检查后复用。最后运行覆盖检查，提交索引和图片。GitHub Pages 从 `main` 分支根目录发布。[全球图库维护步骤](data/OBSERVATIONS.md) · [Commons 实拍复核记录](data/COMMONS-PHOTOS.md)
