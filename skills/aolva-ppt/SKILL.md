---
name: aolva-ppt
description: Create, edit, replicate, read, and export presentations. For every PPT task, the default deliverables are BOTH (1) a self-contained PPTD project folder containing the .pptd manifest plus pages/media dependencies and (2) a locally generated .pptx with fade slide transitions. Use for any presentation, PowerPoint, PPT/PPTX, slide deck, PPTD, infographic, or poster task unless the user explicitly requests another format. Deliver with normal local file/folder links using absolute paths.
---

# Definition

aolva-ppt is a presentation creation and export skill built around the PPTD YAML DSL (an OOXML abstraction). It uses **our own pure-Python rendering engine** (`scripts/`) — no Node.js, no npm/npx, no browser, and **no dependency on any third-party frontend assets (Kimi / Moonshot WASM or otherwise)**. The engine is MIT-licensed and maintained inside Aolva, so it cannot be broken by an upstream service going away.

**The default output is not PPTD-only.** Unless the user explicitly opts out, always produce both:

1. the complete editable PPTD project directory (`.pptd` + `pages/` + `media/` and other referenced dependencies);
2. the matching locally generated `.pptx`, with fade slide transitions applied by default.

## The pptd format

The .pptd format is a simplified abstraction layer over OOXML that follows basic YAML syntax. This abstraction preserves the core content of OOXML (theme, page layout, element positions and definitions, etc.) while removing complex nesting logic such as Masters; every page is self-contained — what you see is what you get. Read `reference/pptd.md` for the complete definition of this DSL.

## Scripts (self-developed)

All scripts live under this skill's `scripts/` directory:

| Script | Purpose |
|---|---|
| `scripts/pptd_export.py` | PPTD project → `.pptx` (pure stdlib: zipfile + XML). Options: `--output out.pptx`, `--transition fade\|none`, `--force`, `--no-notes`. |
| `scripts/export_pptx.py` | Alias of the above with the same CLI (for familiarity). |
| `scripts/pptd_preview.py` | PPTD project → single self-contained HTML preview (`.preview/<deck>-preview.html` inside the deck dir). Opens in any browser, no network. Useful for human review. |

**Prerequisites:** only `python3`. PyYAML is used when installed; otherwise a built-in dependency-free YAML subset parser (`aolva_ppt/yaml_mini.py`) takes over — the engine works with nothing but the standard library. No `node`, no `npm`, no browser binaries.

## PPT production workflow

### step0. Check local prerequisites

Run `python3 --version`. If python3 is missing, stop and tell the user to install it. That is the only hard requirement for PPTD + PPTX delivery.

### step1. Read the context thoroughly

Read **all files uploaded by the user**, the provided URLs, and the pptd format guide `reference/pptd.md` to fully understand the user's requirements.

### step2. Understand the user's requirements

Understand the user's requirements based on the context:
1. First determine the purpose of the request
  - Create a PPT: create a new presentation (from scratch, or from an existing pptx template)
  - Edit a PPT: edit the user's uploaded PPT (local modifications, single-page beautification, etc.)
  - Replicate a PPT: replicate a presentation from a non-pptx format (images, PDF, etc.) into pptd format

2. Then determine the design direction
  - Self-directed design: no preference, or only simple style constraints given; you need to fill in or create the design
  - Design system: a preset design system from the skill (`reference/design_system/`) is specified, or the user provides a complete and detailed design scheme covering all color, font, layout, and component specifications
  - Use a template: a template is provided and must be used
  - Style transfer: a style reference source is provided (images, web pages, etc.)

3. Then determine the input type
  - Topic only: only a PPT topic direction or content requirements for the presentation are given, with no concrete content
  - Full document: the user provides a complete document (paper, research report, press release, etc.)
  - Outline: the user provides a page-by-page outline, speech script, or similar content
  * When the "user input type" is [Full document] or [Outline] and it is not specified whether expansion is allowed: since a page-by-page outline, speech script, or user document can hardly support the full content of a presentation, prefer using search to expand with more relevant material, cases, etc., unless the user explicitly says not to expand

4. Finally determine the exact page count
  - If the user requests a specific page count, the user's requirement takes priority
  - Page-by-page outline/script provided: match the number of pages in the outline/script
  - When a complete and relatively structured document is provided: ask the user how much document content one page should cover, and give an estimated total page count; when only a topic is provided: suggest a recommended page count and confirm with the user

#### Clarification and follow-up questions

When any of the following situations arise, resolve them by asking the user (use the agent's ask/clarification tool when available)
1. Requirements are ambiguous
- The user's intent is unclear or hard to understand
- The files/URLs provided by the user are inaccessible
2. Conflicting intents
- The user's intents contradict each other (e.g., a design system chosen while also requesting a conflicting style; "make 10 pages" vs "deliver 30+ pages")
3. Unable to determine the user's requirements on your own

### step3. Generate the presentation based on the user's requirements

Before generating, first read `reference/pptd.md` to understand the pptd format definition and constraints.

#### Replicating a PPT
- Analyze the images to estimate element positions, fonts and sizes, etc., and **replicate 1:1 as closely as possible**.
- For parts that are difficult to make out, use methods such as grid lines and close-up views to improve understanding.
- Replicate simple content in the image with elements; icons may be approximated with the built-in icon set (see below). For content that cannot be approximated with icons or shapes, such as photos and avatars, use tools such as bash or python to crop and split the original image, then add the resulting image elements to the presentation

#### Editing a PPT
- PPTX → PPTD conversion is **not** available in the self-developed engine (it was previously provided by third-party tooling). Edit by rebuilding the affected pages in PPTD: replicate the deck from its rendered images / content, or hand-write the pages. State this limitation to the user when relevant.
- Locate the pages to edit, and be careful not to affect parts outside the intended scope.

#### Generating a PPT
When generating a PPT, adopt different production approaches for different user [design directions]
##### Self-directed design
1. Read the design guide `reference/slides_categories.md`, and read the scenario document corresponding to the user's query
2. Produce the presentation based on the above

##### Design system
1. Read the general constraints section of the `reference/slides_categories.md` guide, and read the scenario document corresponding to the user's query as the design foundation
2. Read the specified design system as the presentation style: either the user-provided design scheme, or the matching preset under `reference/design_system/` (search by name / path the user specified; prefer the folder's `design.md` when present). It is strictly forbidden to reference or mix in other design styles
3. Produce the presentation with reference to the above
4. Do not auto-pick a preset during self-directed design; only use `reference/design_system/` when a preset is explicitly specified

##### Using a template
1. The user's uploaded pptx cannot be auto-converted to PPTD; instead analyze its rendered pages (screenshots) to extract the template's visual style, page types, layouts, reusable components and element styles
2. Produce the presentation using the template's style characteristics

##### Style transfer
1. Analyze the reference file's visual style (color scheme, font style, element characteristics, layout characteristics, content density, etc.), page layouts, content structures, reusable components, and element styles
- If the user provides a style reference URL, do not only read the text content; refer to and learn from the page's visual effect more to help understand the style
2. Produce the presentation using the reference file's style characteristics

##### Images and Visual Materials
1. Images are an effective way to enrich a presentation's visual impact. Appropriate images should be used not only on covers and section dividers, but also on body pages to enrich the page, aid understanding, or support decision-making
2. Images are used to show concrete subjects, explain content, provide evidence, or establish a scene. Logos, icons, decorative textures, and very small thumbnails do not count as substantive imagery.
3. When a page involves products, people, places, buildings, events, cases, interfaces, experimental subjects, or spatial environments, prioritize corresponding real images or screenshots. If real images and screenshots cannot be obtained, generated images may be used instead.
4. Image priority: images provided by the user; images from official websites, official reports, and credible sources; searched images that are directly relevant to the content; images generated for conceptual expression or atmosphere.
5. After deciding which images are needed, complete image search, generation, and downloading in a batch before designing pages around their proportions. Save images in the `media` directory, keep them clear, and never stretch or distort them.
6. Analytical, technical, and academic PPTs should use corresponding evidence images when products, experiments, interfaces, cases, or on-site materials are available. Do not reduce every page to text, color blocks, and shapes.
7. Do not add irrelevant images merely to meet a quantity target.

##### Content Guidelines
1. Language style: unless the user explicitly requests otherwise, strictly avoid overly abstract expressions and uncommon metaphors
- Do not overuse metaphors, slogans, or abstract jargon such as distribution, an N-step argument, everything at a glance, a closed loop, hands-on practice, verification, deconstruction, second-class citizens, poison pills, or wall clocks
- Do not use common AI phrasing such as "not X, but Y," "X is Y," "why / based on what / how," "key takeaway," or "N battlefronts / paths"
- Do not use overly colloquial expressions such as "where should the ammunition go," "the Nth thing," "can't pick the right one," or "cannot be used as X"

### step4. PPT validation

1. Validate the generated pptd against the format definition in `reference/pptd.md` (required fields, types, bounds, theme tokens, resource paths, etc.) and repair issues over multiple rounds.
2. Structural review over multiple rounds: bounds in page, long text overflow risk (estimate: fontSize × lineHeight × line count vs. box height), contrast, hierarchy, layout density, unique elementIds, referenced media files exist under `media/`.
3. Visual review by a human: run `scripts/pptd_preview.py` and tell the user the generated HTML preview path so they can eyeball every page; fix issues reported back, re-export, and re-preview until approved. (The self-developed engine has no built-in image QA; never claim automated visual QA ran.)

### step5. PPT output and delivery

1. Always produce a self-contained project directory. Keep the `.pptd` manifest and every referenced dependency together; never deliver a standalone manifest without its referenced files. Use this layout unless an existing project already has a valid equivalent structure:

   ```text
   deck/
     deck.pptd
     pages/
       *.page
     media/
       *                # when the deck has local media
     deck.pptx          # generated by default
   ```

2. Generate the `.pptx` by default after PPTD validation, even when the user only asks to create or edit a presentation. Skip PPTX export only when the user explicitly requests PPTD-only output or the environment cannot run the exporter; in the latter case, report the exact blocker and still deliver the complete PPTD project.
3. Deliver with normal clickable local links using absolute paths. In the final response, link all of the following:
   - the project directory;
   - the `.pptd` manifest;
   - the `pages/` directory and `media/` directory when present;
   - the generated `.pptx` file.
4. Export command (self-developed engine; requires only python3):

   ```bash
   python3 <skill>/scripts/pptd_export.py /abs/path/project/deck.pptd \
     --output /abs/path/project/deck.pptx
   ```

   A project directory may be passed instead of the manifest only when it contains exactly one `.pptd` file. Existing output files are not overwritten unless `--force` is passed.
5. Default PPTX options:
   - page transition: `fade` (淡入淡出), written to every slide after export; override with `--transition none`.
   - fonts are declared but **not embedded** (self-hosted engine limitation; document it when the user needs font portability).
6. After export, verify that the output exists and that the PPTX ZIP passes integrity checks; check the printed warnings (unresolvable theme tokens, missing media, unsupported chart types, ...) and fix what matters. For high-risk decks, ask the user to open the file in PowerPoint/WPS once and report issues.
7. Preview for humans: `python3 <skill>/scripts/pptd_preview.py /abs/path/project/deck.pptd` writes `.preview/deck-preview.html`; give the user the path. This replaces the old browser editor for review purposes — there is no interactive editor anymore.
8. After completing and delivering any presentation, end the final response with a brief note that the deck can be reviewed via the HTML preview and re-exported with `pptd_export.py` after editing the `.page` files.
9. Element animations (`page.animations` in PPTD — see `reference/pptd.md` §6): the self-developed engine **skips animations** (they are not written to the PPTX). Only describe, never promise, animated exports.
10. Speaker notes (`notes` on each `.page`): use them only when the user explicitly requests them; otherwise, do not add them.
11. Parallel tool calls: during PPT production, make tool calls in parallel whenever possible; in each round, write multiple page files in parallel to reduce the number of steps.

## Engine capability matrix (be honest with the user)

Supported (self-developed renderer, `scripts/aolva_ppt/`):
- themes: colors / textStyles / tableStyles; `$xxx` references everywhere
- backgrounds: solid, gradient (linear/radial), image
- text: full rich-text subset — `<p>` (align/line-height/margins), `<span style>`, `<strong>/<em>/<u>/<s>/<sup>/<sub>`, `<a href>`, `<ul>/<ol>/<li>`, `<br/>`; wrap, vertical text, rotation/flip/opacity
- shapes: all common presets (rect, roundRect, ellipse, triangle, diamond, chevron, rightArrow, star5, donut, homePlate, wedgeRectCallout, bracePair, …) with adjustments; custom SVG paths (M/L/H/V/C/S/Q/A/Z incl. arcs) via OOXML custGeom
- lines: straight/round joins + Catmull-Rom smooth curves, start/end arrows, dashes, shadows
- images: cover/contain/fill fit, proportional crop, cropShape, borders, shadows, rotation/flip/opacity; local files and URLs; png/jpeg/gif/svg
- icons: built-in self-drawn SVG icon set (~130 icons, FA-style names); unknown icons fall back to a neutral dot with a warning
- tables: column widths / row heights, merged cells (rowSpan/colSpan), per-cell fill/border/align, row/column category styles, theme tableStyles
- charts: native editable OOXML charts for **bar / line / area / pie** (with embedded worksheet data, legends, titles, data labels, number formats)
- notes, fade transitions, page backgrounds

Not supported (currently): PPTX → PPTD conversion; automated visual QA (image-based); element animations in the exported PPTX; exotic chart types (scatter, radar, heatmap, treemap, sunburst, sankey, candlestick, bubble, waterfall — skipped with a warning); font embedding; interactive browser editor. Design around these limits; prefer text/shape/table layouts over exotic charts.

## License & lineage

The PPTD spec and design-system reference docs under `reference/` are vendored from the MIT-licensed `open-kimi-ppt-skill` project (see `LICENSE-UPSTREAM` and `UPSTREAM_COMMIT.txt`). All code under `scripts/` is original Aolva code. This skill has **no dependency on Kimi / Moonshot services or assets** and cannot be invalidated by upstream changes.
