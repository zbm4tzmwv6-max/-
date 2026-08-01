---
name: curate-craft-beer-article-images
description: Curate and deliver real, verifiable images for Chinese craft-beer WeChat/公众号 brewery profiles, beer launches, tap takeovers, event previews, and related articles. Use when the user asks 给文章配图, 公众号配图, 找10/15/20张图片, 参考Instagram, 图片预览, 图片下载, or 打包配图. Retrieve non-AI images, prioritize official sources, map images to article structure, normalize them as high-resolution 16:9 assets, show every image individually, preserve provenance, and provide a mandatory ZIP download.
---

# Curate Craft Beer Article Images

Deliver a finished image set, not search advice or a collection of links.

## Enforce the delivery contract

- Use real published photographs or official artwork. Do not generate images, imitate official assets, redraw, composite, or substitute diagrams unless the user explicitly asks for design work.
- Do not reuse one source image through multiple crops, enlargements, color variants, or detail cuts to fill the requested count.
- Deliver exactly the requested number of usable images.
- Show every image as an individually visible preview in the response. Do not use a collage or make the user open a page to discover what was selected.
- Create one ZIP containing all final images and their provenance manifest. A ZIP download is mandatory even when every preview works.
- Treat the work as incomplete if previews are broken, the ZIP is missing, the download fails, the count is short, or packaged files cannot be opened.

## Plan the visual story

Read the article or current draft before searching. Build a numbered shot list in article order.

For each featured beer, default to:

1. One complete product or label image.
2. One official scene image: pour, filled glass, taproom, bar, brewing, ingredients, barrel, event, or drinking moment.

Distribute the remaining slots across the subjects the article actually discusses:

- brewery location, exterior, city, or landscape;
- taproom and serving atmosphere;
- founder, brewer, or team;
- brewhouse, cellar, equipment, or process;
- hops, fruit, grain, barrels, or proprietary technique;
- representative beers and the beers being launched;
- awards, rankings, festival recognition, or community standing;
- anniversary, current event, collaboration, or other recent development;
- lineup, opening image, and closing atmosphere.

Avoid a set dominated by cans, bottles, labels, or near-identical tabletop shots. For 20 images, group the shot list into five article chapters of four images when the article supports that structure.

## Search in fixed source order

Use this hierarchy:

1. Brewery official Instagram.
2. Brewery official website or media kit.
3. Official Facebook or another official social account.
4. Official collaborator, importer, event organizer, or credited photographer.
5. Reputable beer or local industry media.
6. Untappd, BeerAdvocate, or another community platform.

Aim for 70–80% of the set from official Instagram or the official website. Keep the source system visually coherent. Prefer the original post or publisher page over an aggregator, repost, search thumbnail, or uncredited consumer upload.

Record the canonical source URL at selection time. Verify that the page and depicted subject match the proposed caption. Do not infer an award, person, beer, process, date, or location from appearance alone.

## Acquire stable local assets

Download the largest accessible version of the selected real image. If a remote image cannot render reliably, save the actual published image locally or capture the published image at the highest usable resolution and remove surrounding page chrome. Preserve the original page URL.

Normalize final files as follows:

- 16:9 landscape, preferably 1600×900 or larger;
- crop without stretching;
- keep faces, containers, labels, award text, and other primary subjects complete;
- reject low-resolution, visibly compressed, heavily watermarked, cluttered, or untraceable images;
- use sequential filenames beginning with `配图01`, `配图02`, and so on.

For a rare historical or award image that cannot meet the preferred resolution, keep it only when it adds unique evidence. Mark the exception explicitly instead of silently upscaling it.

## Create the manifest

Create a UTF-8 CSV with these exact columns:

```text
number,filename,theme,insertion,purpose,source_platform,original_url,is_official,rights_note
```

Use one row per image. `number` must run continuously from 1 to the requested count. `is_official` must be `yes` or `no`. Use `rights_note` to preserve a photographer credit, publisher credit, usage condition, or the need to confirm commercial-use permission.

## Validate and package

Run the bundled script after the final crop and manifest are ready:

```bash
python3 scripts/package_delivery.py \
  --images-dir /absolute/path/to/images \
  --manifest /absolute/path/to/配图说明.csv \
  --output /absolute/path/to/品牌名_公众号配图.zip \
  --expected-count 20
```

The first run performs automated checks and stops at `requires_manual_review`. It does not create the ZIP.

Open every final image and its original source page. Confirm all of the following manually:

- the image content matches `theme`, `insertion`, and `purpose`;
- the depicted beer, brewery, person, award, process, event, and location are correctly identified;
- the original URL displays or credibly publishes the selected image;
- `is_official` reflects the actual account or publisher identity;
- photographer, publisher, and usage notes are preserved;
- no two files are alternate crops or edits of one source image.

Only after that review, rerun with the confirmation flag:

```bash
python3 scripts/package_delivery.py \
  --images-dir /absolute/path/to/images \
  --manifest /absolute/path/to/配图说明.csv \
  --output /absolute/path/to/品牌名_公众号配图.zip \
  --expected-count 20 \
  --confirm-manual-review
```

Never add the flag merely to bypass the gate. The script cannot determine image semantics, account authenticity, source-image correspondence, or commercial usage rights.

The script checks sequence, count, filenames, image readability, dimensions, aspect ratio, exact duplicates, likely visual duplicates, URL structure, and official-source share. After manual confirmation, it creates:

- the final ZIP;
- `配图说明.md`;
- `配图预览.html`;
- `校验报告.json`.

If the script flags likely visual duplicates, inspect them. Replace repeated source material. Use `--allow-similar` only after confirming the files are genuinely different photographs, not alternate crops or edits of the same original. If official-source share is below 70%, search again; use `--allow-low-official-ratio` only when official material is genuinely unavailable and state the exception in the delivery.

Open representative images and the generated preview page before delivery. Confirm the ZIP can be listed and extracted.

When persistent file storage is available, use its applicable file skill to save the final ZIP before responding. A transient link alone does not satisfy the requirement when persistent delivery is supported.

## Present the result

List images in article order. For every image, show:

```markdown
### 配图01｜图片主题

![可见预览](sandbox:/absolute/path/to/image.jpg)

- 建议位置：
- 文章作用：
- 来源／平台：
- 原始链接：
- 官方素材：是／否
```

After the final preview, provide one clearly labeled ZIP download link. Mention any rights or resolution exceptions next to the affected image and in the manifest.

## Apply the completion gate

Do not claim completion until all answers are yes:

- Is the requested count exact?
- Is every item a distinct, real, verifiable asset?
- Does every image have a visible preview?
- Are all previews stable?
- Are final files 16:9 and usable at publication size?
- Does every image have complete provenance and an original URL?
- Is the set structured around the article rather than dominated by product packs?
- Does the ZIP contain every final image and the manifest?
- Has the ZIP been opened or listed successfully?
- Is one unified ZIP download link present in the final response?
