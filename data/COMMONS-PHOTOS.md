# 补充摄影的核对方法

这批照片从缺图名录出发，在 BirdNET+ 的种级记录中核对学名与已有的 Avibase 编号，取得 Wikidata QID。Wikidata 的物种阶元、学名和首选图像（P18）用于寻找候选文件。P18 也可能指向标本、画作或栖息地风景。

2026 年 11 月 20 日检查的 323 种未标记灭绝、当时缺图的物种中，304 种能对应确定的 QID，取得 127 个学名与物种阶元一致的候选图。20 个文件有明确的相机型号。进一步比对了文件名和说明中的鸟名、拍摄地与物种分布、署名及许可，实际查看入选照片，排除风景、标本、扫描图、地理范围或分类含义不合的图片，以及已由另一来源补齐的记录。

核定的文件列在 [commons-reviewed.json](commons-reviewed.json)。每项记下 AviList 物种号、Wikidata QID、Commons 文件页编号、原文件 SHA-1 和用于核对的原始名称。对沿用旧亚种名的 *Tunchiornis ochraceiceps luteifrons*，另记录了[康奈尔大学鸟类学实验室的分类修订](https://www.birds.cornell.edu/clementschecklist/updates-and-corrections-october-2025/)。图像记录只描述为活体实拍，未从画面推断是否为野外个体。

运行下列命令会核对锁定的原文件版本、相机型号、鸟名、作者与许可，再生成两份 WebP。详情图长边最多 1920 像素，卡片预览长边最多 480 像素，较小的原图保留原尺寸。原片和两份图的实际尺寸都记在清单里。默认把合并用的记录写到 `data/commons-additions.part`。原文件替换或许可资料发生无法确认的变化时，需要重新核对。

```sh
python scripts/import_commons_photos.py
```

每张图保留作者、文件页、原始图像地址、许可与转换说明。请依照对应文件所列的 CC BY 或 CC BY-SA 许可使用。可在 [Wikimedia Commons 复用说明](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia) 查阅署名与共享条款。
