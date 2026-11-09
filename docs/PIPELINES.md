# How the pipelines work

[README](../README.md) · [User guide](USER_GUIDE.md) · [Developer guide](DEVELOPMENT.md) · [Measurements](MEASUREMENTS.md)

What happens between pressing **Generate** and the finished picture: for every page, what you do and what the app does
inside. The diagrams are schematic; the [developer guide](DEVELOPMENT.md) has the protocol and the code paths.

### <img src="icons/loader-circle.svg" width="20" height="20" alt=""> The way of a job

Every page turns its form into a **job**. Jobs wait in one queue in the main process, so they keep running while you
switch pages, and they run **one at a time**, because all engines share the unified memory. The queue sends each job
to the engine that runs its model, and a result reaches the page only after the content check has passed it.

```mermaid
flowchart TD
    P["Page: Text, Image, Inpaint, Canvas, Video, Illusion, Restore, Upscale, LoRA comparison"] --> F["Form becomes a job: model folder, prompt, style, size, steps, seed, LoRAs"]
    F --> PC{"Prompt check passed?"}
    PC -- "no" --> RF["Refused, or the consent question for edits of a real photo"]
    PC -- "yes" --> Q["Queue: one job at a time; Pictures = N gives N jobs with seeds counting up"]
    Q --> R{"Which engine?"}
    R -- "Krea 2, Ideogram 4, FLUX 3; FLUX.1 and FLUX.2 klein without an input picture when MLX is chosen" --> MLX["MLX"]
    R -- "Anima, Wan 2.2 video, Upscale" --> CUI["ComfyUI"]
    R -- "all other models, Restore" --> DIF["Diffusers"]
    DIF --> LD["Model loaded by the memory plan: in memory, compressed, staged text encoder or SSD streaming"]
    MLX --> G["Generation, progress per step"]
    CUI --> G
    LD --> G
    G --> CC{"Content check passed?"}
    CC -- "no, or it could not check" --> DEL["Result deleted, reason shown"]
    CC -- "yes" --> H["Marked as AI generated; History, Favorites, large view"]
```

- **Engines** are separate Python processes that read requests on stdin and report progress on stdout. Only one of
  them keeps a model in memory: before another engine starts a job, the previous one unloads its model.
- **MLX or Diffusers**: Krea 2, Ideogram 4 and FLUX 3 Image Klein run only with MLX (FLUX 3 with flux3-mlx, see
  below). FLUX.1 and FLUX.2 [klein] in repository layout run with
  MLX when *Settings → Runtimes* prefers it (or chooses automatically and MLX is installed), but only without an input
  picture and without a control picture. Everything else of these families goes to Diffusers.
- **FLUX 3 Image Klein** (`engines/mlx/flux3.py`) runs with flux3-mlx instead of mflux: it reads Black Forest Labs'
  own files (`model.safetensors`, `ae.safetensors`, `text_encoder/`) or the MLX-quantized repositories made for it. When
  transformer and text encoder do not fit together, the prompt is encoded before the transformer is loaded, so the peak
  is the larger of the two (16 GB Macs: the 6 and 8 bit repositories). LoRAs are put beside its linear layers (also the
  quantized ones), from Black Forest Labs', diffusers' or kohya's names. The optional prompt upsampler (Black Forest
  Labs' flux-3-image-klein-pup, 4 bit, a helper model) runs with mlx-lm before the transformer is loaded and is freed
  again; its caption becomes the job's note. A job with an input picture is not upsampled (that needs the upsampler's
  vision part).
- **The content check** is a long-lived process of the Diffusers runtime. It looks for nudity and estimates the age of
  every face; nudity with a face that is likely a minor is always blocked, any nudity in safe mode. Videos are checked
  on six frames. It **fails closed**: a result it could not check is not shown. Pictures that pass get IPTC/XMP
  metadata saying they are AI generated; ComfyUI marks its videos itself.
- The finished job goes into the **History** with all its settings, so *Use these settings* can bring it back, model
  included.

### <img src="icons/memory-stick.svg" width="20" height="20" alt=""> Loading a model: the memory plan

The Diffusers engine never simply loads a model and hopes. Every model has a **memory plan** worked out from the
sizes of its parts: the budget is the Mac's memory minus a reserve (a fifth, at least 4 GB, or the reserve set in
*Settings*), and the plan picks the best quality that fits.

```mermaid
flowchart TD
    M["model.json: parts and their sizes, file format"] --> P["Try in order: all 16 bit; text encoder 8 bit; text encoder staged; denoiser 8 bit"]
    P --> F{"Fits the memory budget?"}
    F -- "yes" --> A{"SSD streaming set to Always?"}
    A -- "no" --> MEM["Load into memory; 8-bit parts come from a one-time cache"]
    F -- "no" --> S{"16-bit denoiser, streaming not off?"}
    A -- "yes" --> S
    S -- "yes" --> SF{"Fits with one block of the denoiser in memory?"}
    SF -- "yes" --> ST["SSD streaming: denoiser cut into blocks once, one block loaded at a time"]
    SF -- "no" --> FB{"Fitted without streaming?"}
    S -- "no" --> FB
    FB -- "yes" --> MEM
    FB -- "no" --> RF["Refused: needs about N GB, with a hint to MLX for FLUX"]
```

- **Staged text encoder**: the text encoders are loaded only to encode a new prompt and freed before denoising. The
  embeddings are kept, so the same prompt again costs nothing.
- **Compression** with optimum-quanto happens once and is cached next to the model, so later loads are quick. Automatic
  compression goes down to 8 bit; 4 bit comes from GGUF files (or from MLX), whose size is taken as it is.
- **GGUF and FP8**: GGUF files stay packed and are unpacked inside the layers. FP8 checkpoints, which the Apple GPU can
  not compute, become 8-bit GGUF on import. Where a GGUF model does not fit, it streams like a 16 bit one: its
  blocks are unpacked into the streaming cache once (the file is read into memory for that, one time), later
  loads read only the cache.
- **SSD streaming** needs free disk space of about twice the denoiser plus 5 GB for its cache (next to the model, or
  in *Settings → Folders → SSD streaming cache*). The first run shows *Preparing SSD streaming (one-time)*.
- **Large pictures**: the VAE decodes in tiles, SDXL computes attention in slices above about 1536 × 1536, and on
  M1/M2, where bfloat16 is slow, models that allow it compute in float16.

The MLX engine has a plan of its own (mflux, 8 or 4 bit), and ComfyUI keeps the weights as they are and frees the
text encoder when the denoiser needs room.

### <img src="icons/type.svg" width="20" height="20" alt=""> Text to image

1. Open **Text** and choose the **Model** in the panel on the right.
2. Describe the picture. Set **Style**, **Size**, **Steps**, **Guidance**, **Sampler**, **Seed**, **Pictures**, up to
   three **LoRAs** and, where the model has one, **Not in the picture**.
3. Press **Generate** (or ⌘↩). The results appear as tiles under the prompt; a click opens the large view. **×** takes
   a tile out of the list (also a cancelled or failed one), and the pointer on **ⓘ** shows a job's details.

```mermaid
flowchart TD
    F["Form"] --> J["Job: style name, sampler only if the model has it, LoRAs that fit the model"]
    J --> Q["Queue: one job per picture, seed, seed + 1, ..."]
    Q --> ST["Style template wraps the prompt; the style's negative words are added"]
    ST --> E["Engine loads the model if another one is loaded"]
    E --> L["LoRAs loaded and checked; trigger words put in front of the prompt"]
    L --> SA["Sampler and noise schedule set, else the model's own"]
    SA --> TE{"Text encoder staged?"}
    TE -- "yes" --> EN["Encode the prompt, free the encoder, keep the embeddings"]
    TE -- "no" --> DN["Denoising, one progress step per step"]
    EN --> DN
    DN --> V["VAE decodes the picture, in tiles"]
    V --> CC["Content check, then History"]
```

- **Switching the model keeps the settings.** Steps, guidance, seed and size stay, so that models can be compared with
  the same ones; a **!** shows what the new model suggests and **Model defaults** sets it. Only a size the new model
  can not compute changes (in the same proportions) and comes back on a model that can. A chosen sampler stays chosen (a
  model without it runs its default, a **!** says so). LoRAs of another family and a control type the new model
  has not are dropped. The very first model of a page brings all its defaults.
- **Seed**: empty means random. With **Pictures** above 1, the queue makes one job per picture with seeds counting up,
  so every picture of a series can be made again.
- **Styles** live in the job by name; the prompt stays as written, and the engine gets the styled prompt. Models
  without a negative prompt (FLUX) use only the template.
- All image families run here, on the engine chosen above. Inpaint-only models are not offered.

### <img src="icons/images.svg" width="20" height="20" alt=""> Image to image

1. Open **Image** and **Choose a picture** (or drop one onto the field).
2. Describe what the picture should become.
3. Set **Change** (0.05–1). Tick **Own size instead of the picture's proportions** for another size.
4. Press **Generate**.

```mermaid
flowchart TD
    I["Picture and prompt"] --> SZ["Size: the picture's proportions at the model's own pixel count, or own size"]
    SZ --> FAM{"Which kind of model?"}
    FAM -- "FLUX.2, Qwen-Image 2.1" --> REF["The picture is a reference: the model edits after the prompt, Change is not used"]
    REF --> QT{"Qwen-Image 2.1 with a staged text encoder?"}
    QT -- "yes" --> NO["Refused: it reads the picture with its text encoder"]
    QT -- "no" --> G["Generation"]
    FAM -- "SD, SDXL, SD 3.5, FLUX.1, Chroma, Qwen-Image" --> CN{"Control picture as well?"}
    CN -- "no" --> IMG["Image-to-image pipeline on the loaded parts; Change sets how much noise is added"]
    CN -- "yes" --> CIMG["ControlNet image-to-image pipeline, not for SD 3.5"]
    IMG --> G
    CIMG --> G
    FAM -- "Anima on ComfyUI" --> CF["The picture is encoded; Change sets the denoise"]
    CF --> G
```

- **Change** is the share of the picture that is noised and painted again: at 0.3 colours and details change, at 0.6
  the motif, above 0.8 little of the picture remains.
- The image pipelines are built on the parts that are already loaded, so switching between Text and Image does not
  load the model again.
- FLUX jobs with an input picture always run with Diffusers, never with MLX.
- A prompt that asks for intimate content from an input picture first asks the **consent question**.

### <img src="icons/eraser.svg" width="20" height="20" alt=""> Inpainting

1. Open **Inpaint** and choose the picture.
2. **Paint** over the part that is to change (**Erase**, **Size**, undo and the bin help).
3. Describe what should appear there, or leave the prompt empty to remove something.
4. Set **Change** (default 100 %) and press **Generate**.

```mermaid
flowchart TD
    P["Picture and painted mask: white is painted anew"] --> IP{"Has the model an inpainting pipeline?"}
    IP -- "no" --> NO["Refused: use an SDXL, SD 3.5, FLUX.1 or Chroma model"]
    IP -- "yes" --> GR["Mask grown a little, so old and new parts blend"]
    GR --> SM{"Mask smaller than a third of the picture?"}
    SM -- "yes" --> CR["Area around the mask cut out and painted at the model's full size"]
    SM -- "no" --> WH["The whole picture is painted"]
    CR --> RUN["Inpainting pipeline, Change as strength"]
    WH --> RUN
    RUN --> PB["Painted area put back in place"]
    PB --> BL["Only the masked area comes from the new picture; the rest stays pixel-exact"]
```

- **Families**: SD 1.x, SD 2.x, SDXL, SD 3.5, FLUX.1, Chroma and Qwen-Image. Older imports without that note in their
  manifest are judged by their family.
- **Small masks** are painted in a cut-out of the picture's proportions, so what the prompt asks for lands in the
  mask instead of somewhere else in the picture.
- **Inpaint-only models** (such as *SD 1.5 Inpainting*) appear only here; a text or image job on them is refused. They
  give the cleanest borders.
- A mask and a control picture can not be combined.

### <img src="icons/frame.svg" width="20" height="20" alt=""> AI Canvas

1. Open **Canvas**, **Add a picture** or start in an empty frame.
2. With **Move** (V) drag the orange frame where the next picture belongs, for example half over the edge of a picture.
3. Optionally paint with the **Mask brush** (B) inside the frame.
4. Describe what should appear and press **Generate**. **Export PNG** saves the whole canvas.

```mermaid
flowchart TD
    FR["Frame on the canvas"] --> W{"What is in the frame?"}
    W -- "nothing" --> NEW["A new picture at the frame's size"]
    W -- "partly a picture" --> EXT["Extend: empty parts become the mask"]
    W -- "a picture with mask strokes" --> REP["Repaint: the strokes become the mask"]
    W -- "a picture, no strokes" --> VAR["Variation: image to image with Change 0.1 to 0.9"]
    EXT --> PF["Empty part prefilled with the colours along the edge, wide transition"]
    PF --> INP["Inpainting pipeline at full strength"]
    REP --> INP
    NEW --> Q["Queue, like every other job"]
    VAR --> Q
    INP --> Q
    Q --> L["Result placed as a new layer in the frame"]
```

- The start picture is what lies under the frame, with empty parts in neutral grey. When **extending**, every empty
  pixel takes the colour of the nearest picture pixel, strongly blurred, so light and colours continue instead of
  starting from grey; the whole frame is painted, without a cut-out.
- **Models**: all image models except ComfyUI and inpaint-only ones. Extending and repainting need SDXL, SD 3.5,
  FLUX.1, Chroma or another model with an inpainting pipeline; other models paint new pictures only (and variations,
  where they can do image to image). The panel always says what will happen.
- The canvas, with pictures, view, prompt and model, is kept after a restart.

### <img src="icons/person-standing.svg" width="20" height="20" alt=""> ControlNet and pose

**A control picture in Text or Image:**

1. Choose a **Control** kind: Pose, Depth, Edges, Line art, Scribble or Tile (only what the model has is offered).
2. Choose the control picture. Leave **It is a photo: prepare it first** on for a normal photo.
3. Set the **Weight** (0–2) and press **Generate**.

**From the Pose editor:** build people from a **Template**, drag their points, or detect them **From a photo**, then
**Use in Text to image**. The skeleton arrives as a Pose control picture that needs no preparing, together with its
size.

```mermaid
flowchart TD
    C["Control picture"] --> PH{"A photo to prepare first?"}
    PH -- "yes" --> PRE{"Which kind?"}
    PRE -- "Pose" --> DW["DWPose finds the people: body, hands, face, drawn as OpenPose"]
    PRE -- "Depth" --> DA["Depth Anything V2 estimates the depth"]
    PRE -- "Edges, Line art, Scribble" --> CV["OpenCV traces the edges"]
    PRE -- "Tile" --> TL["The photo itself"]
    PH -- "no" --> RS["Resized to the picture's size"]
    DW --> RS
    DA --> RS
    CV --> RS
    TL --> RS
    RS --> CM["ControlNet of the family, downloaded once"]
    CM --> FT{"Fits next to the model?"}
    FT -- "16 bit fits" --> RUN["ControlNet pipeline, image-to-image variant with an input picture"]
    FT -- "after staging the text encoder, or in 8 bit" --> RUN
    FT -- "no" --> NO["Refused: not enough memory"]
```

- **ControlNets**: SDXL uses one union model (xinsir ProMax) for all kinds, FLUX.1 the Union Pro 2.0 with its makers'
  recommended scales, SD 1.5 one ControlNet 1.1 per kind, SD 3.5 Medium and Large their own Depth and Canny models (and
  Tile for Large).
- The helper models (DWPose, Depth Anything) are downloaded on first use into the helper folder. The pose editor's
  **From a photo** runs the same DWPose detection through the Diffusers runtime.
- A ControlNet needs memory next to the model (its weights and about half the model's activations, counted in the
  job's planned peak): if it does not fit in 16 bit, the engine first stages the text encoder, then tries 8 bit
  (compressed once and cached).

### <img src="icons/sparkles.svg" width="20" height="20" alt=""> Illusion

1. Open **Illusion** and pick a **Hidden pattern**: Spiral, Rings, Checkerboard, Stripes, Text or Own picture; shape
   it with **Density**, **Blur** and **Invert**.
2. Set **Pattern strength** (about 0.8 subtle, 1.2 clear, 1.6 dominant).
3. Describe the picture the pattern hides in and press **Generate**.

```mermaid
flowchart LR
    PE["Pattern editor draws the pattern at the picture's size"] --> J["Job: control kind Illusion, weight = pattern strength, no preparing"]
    J --> SD{"SD 1.5 model?"}
    SD -- "yes" --> SZ["Size limited to 768 px on the longer side"]
    SD -- "no, SDXL" --> CN["QR Code Monster ControlNet, downloaded once"]
    SZ --> CN
    CN --> RUN["ControlNet pipeline: light parts of the pattern become bright, dark parts dark"]
```

- Only **SDXL** and **SD 1.x** models are offered: the pattern ControlNet (monster-labs QR Code Monster, 5 GB for SDXL,
  v2 for SD 1.5) exists for these two.
- Styles, LoRAs, sampler and seed work as in Text to image.

### <img src="icons/clapperboard.svg" width="20" height="20" alt=""> Image to video

1. Install the **ComfyUI** runtime and a **Wan 2.2** model (Models → Recommended).
2. Open **Video**, choose the **Start picture** and describe the movement, camera and mood.
3. Choose **Length** (1–5 s) and **Resolution** (480p or 720p) and press **Generate**.

```mermaid
flowchart TD
    S["Start picture and prompt"] --> SZ["Size: short side 480 or 704 px in the picture's proportions"]
    SZ --> Q["Queue, routed to ComfyUI"]
    Q --> SV["ComfyUI runs as a hidden server on 127.0.0.1; the model files are linked, not copied"]
    SV --> FR["Frames from length and frame rate, as 4n + 1"]
    FR --> W{"Wan 2.2 14B?"}
    W -- "yes" --> TS["Two stages: the high-noise model for the first half of the steps, the low-noise model for the rest, each with its 4-step LoRA"]
    W -- "no, 5B" --> OS["One sampler from the start picture's latent"]
    TS --> DEC["VAE decodes all frames"]
    OS --> DEC
    DEC --> MP["MP4, marked as AI generated"]
    MP --> CC["Content check on six frames, then History"]
```

- Video takes far longer than pictures: on an M2 with 24 GB a one-second clip at 480p took about 8 minutes, a
  five-second clip 110 minutes, the engine at 7 to 10 GB (MEASUREMENTS 7ay).
- Styles and LoRAs are not used for video; one job makes one clip.

### <img src="icons/maximize-2.svg" width="20" height="20" alt=""> Upscale

1. Open **Upscale** (or press **Upscale** in the large view of any picture).
2. Choose the picture (up to 2048 px on its longer side) and **2×** or **4×**.
3. Press **Enlarge**.

```mermaid
flowchart LR
    P["Picture"] --> Q["Queue: an upscale job needs no model of yours, routed to ComfyUI"]
    Q --> D["Real-ESRGAN x4plus, 64 MB, downloaded once"]
    D --> UP["Enlarged 4 times, tile by tile"]
    UP --> F{"2× chosen?"}
    F -- "yes" --> DOWN["Scaled down to twice the size, Lanczos"]
    F -- "no" --> OUT["PNG"]
    DOWN --> OUT
    OUT --> CC["Content check, then History"]
```

- Real-ESRGAN adds detail instead of blur. ComfyUI's model upscaler works on tiles, so large pictures do not need
  much memory.

### <img src="icons/wand-sparkles.svg" width="20" height="20" alt=""> Restore

1. Open **Restore** and choose the photo. A black-and-white or toned photo is recognised and gets colouring switched on;
   a photo with a colour profile (Display P3, HDR) is converted to sRGB first. The faces are found and shown as frames,
   which can be moved or left out.
2. Pick a **template** (*Black and white, damaged*, *Black and white to colour*, *Colour cast (red or yellow)*, *Faded
   colour photo*, *Only colour it*, *Heavy damage (creases, holes)*, or your own), or choose the steps and their
   strengths yourself.
3. Paint over scratches, creases, spots and holes with the brush, set the guard rails and your own rules, and add a
   note on what the photo shows.
4. Press **Preview** for a part of the photo (compare it with the slider), then **Restore** (or ⌘↩).

```mermaid
flowchart TD
    O["Photo, read as sRGB"] --> C{"Correct colour cast and contrast?"}
    C -- "yes" --> CO["White balance, levels with soft light tones, local contrast, without a model"]
    C -- "no" --> R{"Repair damage with AI?"}
    CO --> R
    R -- "yes" --> LA["Painted damage filled from its surroundings by LaMa, or OpenCV without it"]
    LA --> AI["FLUX.2 edits the photo: note, fixed rules and own rules as the prompt"]
    AI --> CP["Compose: with the lock, only the painted places come from the AI"]
    CP --> GR{"Guard rails kept? Change within the limit, faces the same"}
    GR -- "no" --> NO["Refused with the reason"]
    GR -- "yes" --> DE{"Rebuild soft details?"}
    R -- "no" --> DE
    DE -- "yes" --> ES["Real-ESRGAN: made as much smaller as the photo is soft, four times larger, to its size or twice"]
    DE -- "no" --> FA{"Restore faces?"}
    ES --> FA
    FA -- "yes" --> CF["CodeFormer restores each face framed on the page, taken from the photo before the AI steps"]
    FA -- "no" --> COL{"Colour a black-and-white photo?"}
    CF --> COL
    COL -- "yes" --> DD["DDColor adds colour; the brightness stays the photo's own"]
    COL -- "no" --> SH{"Less grain, sharper details?"}
    DD --> SH
    SH -- "yes" --> SP["Brightness denoised, edges sharpened, colour smoothed"]
    SH -- "no" --> OUT["Restored photo, content check, History (a preview: only the compare slider)"]
    SP --> OUT
```

- **Restore always runs with Diffusers.** Correcting, colouring and sharpening need no model of yours; the AI repair
  needs a **FLUX.2** model and refuses others, because it edits the photo instead of painting it anew. Without paint it
  repaints the whole photo: soft clothing and leaves get real detail, which Real-ESRGAN can not make up.
- **Faces** are taken from the photo before the AI steps: the repair may turn faces into other people, and
  Real-ESRGAN's texture would turn into wrinkles. CodeFormer (non-commercial licence) is blended in by its strength.
- **Guard rails**: the fixed rules (only remove damage; keep composition, people, faces, clothing, objects, writing;
  add or invent nothing) plus your own; with **Keep the original outside the painted damage** the result is put
  together from the original and the repaired places only; **Allowed change** (default 6 %) limits how much the shapes
  may change, measured on the blurred brightness so grain and dust do not count; **Refuse results whose faces changed**
  compares the faces found by DWPose before and after (number and position).
- **DDColor** works on the brightness of the photo and returns only colour, so no shape or detail can change. Helper
  models (LaMa, DDColor, Real-ESRGAN, CodeFormer with YuNet) are downloaded once.

### <img src="icons/layers.svg" width="20" height="20" alt=""> LoRAs

**Finding and installing:** *Models → Installed*, **LoRAs for a model** searches Civitai and Hugging Face for LoRAs
made for exactly this model's base; **Install** puts one into the import queue. LoRAs can also be added on
*Models → Add* like a model.

```mermaid
flowchart TD
    FI["LoRA finder: public search on Civitai and Hugging Face, no token sent"] --> IN["Install: into the import queue"]
    IN --> DL["Downloaded; recognised as a LoRA by its layer names"]
    DL --> HI["Hint from the source: base model on Civitai, base_model of the Hugging Face card, or Civitai by the file's hash"]
    HI --> ST{"Do its layers tell the family?"}
    ST -- "yes" --> SB["Family and sub-base from the layers and their sizes"]
    ST -- "they leave a choice" --> MD["The metadata of the training tool decides"]
    MD --> SB
    ST -- "they tell nothing" --> HN{"Does the metadata or the hint tell?"}
    HN -- "yes" --> SB
    HN -- "no" --> NO["Refused, never filed as SDXL just in case"]
    SB --> MF["lora.json: family, sub-base, trigger words; preview and its makers' description"]
```

**Using a LoRA:** add up to three in the **LoRAs** section of a generate page, each with its weight; only LoRAs that
fit the chosen model's family and sub-base (FLUX.2 [klein] 4B, 9B, [dev]; Wan 5B, 14B) are offered.

```mermaid
flowchart TD
    J["Job with LoRAs"] --> MM{"Made for this model?"}
    MM -- "no" --> NO["Stopped with the reason"]
    MM -- "yes" --> FM{"LoKr or LoHa?"}
    FM -- "yes" --> NO
    FM -- "no" --> CV["Converted where needed: peft dumps, FLUX.1, Chroma and Z-Image in ComfyUI names, ai-toolkit SDXL names, Qwen-Image 2.1 gate_up split"]
    CV --> SS{"Model streamed from the SSD?"}
    SS -- "no" --> LD["Loaded as adapters; a text encoder part that does not load is left out"]
    SS -- "yes" --> MG["Factors merged into each block as it loads"]
    LD --> CK{"At least 90 % of its layers found their place?"}
    MG --> CK
    CK -- "no" --> NO
    CK -- "yes" --> GO["Weights set; trigger words put in front of the prompt"]
```

- The **90 % check** counts the LoRA's denoiser layers that really got the adapter (with streaming: matched by name
  and size before anything is generated). A LoRA that only fits the text encoder must have arrived there.
- **Compare strengths** (LoRA page) queues the same prompt and seed at up to eight strengths between −2 and 3; strength
  0 is one picture without any LoRA, and a second LoRA of the same family can be compared alongside.
- The LoRA page shows what the makers' page says (description, recommended settings, example prompts), read once
  and kept as `info.json` next to the LoRA.

**Training:**

1. Open **Training**, give the LoRA a **Name** (the **trigger word** is made from it) and choose the **Model to train on**.
2. **Add pictures** or **Add a folder** (10–30 pictures; `.txt` files of the same name are captions).
3. Choose a **Preset** or set steps, resolution, rank and learning rate, and **Start the training**.

```mermaid
flowchart LR
    T["Training form"] --> UL["Engines unload their models; no job starts meanwhile"]
    UL --> W{"Which model?"}
    W -- "SDXL" --> SD["Diffusers trainer"]
    W -- "FLUX.2 klein, Krea 2" --> MX["MLX trainer, mflux"]
    SD --> LC["Phase, step, loss curve, time left"]
    MX --> LC
    LC --> LO["New LoRA in the LoRA folder, like an imported one"]
    LO --> CMP["Compare strengths"]
```

### <img src="icons/download.svg" width="20" height="20" alt=""> Model import

1. Open **Models → Add** and choose the source: **Hugging Face**, **Civitai**, **File** or **Folder**.
2. Enter the repository, link or path (for Hugging Face optionally a **File in the repository**), a **Name** if you
   like, and the compression (*Compress when needed*, *Do not compress*, 8 bit, 4 bit).
3. **Check** shows what it is, the download size and the memory it needs, before anything is downloaded.
4. **Download** or **Import** (**Import anyway** when it needs more memory than the Mac has).

*Models → Recommended* runs the same import for a tested list.

```mermaid
flowchart TD
    S["Source: Hugging Face, Civitai, file or folder"] --> K{"What is it?"}
    K -- "Civitai link" --> CI["Civitai names the type and base model of the version"]
    K -- "folder with a manifest" --> IP["Used in place, nothing copied"]
    K -- "a LoRA file" --> LR["LoRA import, see LoRAs"]
    K -- "repository without a full model" --> LS["Its .gguf and .safetensors files listed to pick from"]
    K -- "repository or model file" --> INS["Inspect without downloading weights: architecture, layout, sizes"]
    CI --> INS
    INS --> PL["Memory plan, with SSD streaming as a way out"]
    PL --> CH["Check: label, download size, memory, compression"]
    CH --> RU["Files another model already has are linked or copied"]
    RU --> DW["The rest downloaded; a single file gets its base parts from the base repository; FP8 becomes 8-bit GGUF"]
    DW --> MF["model.json: architecture, family, sub-base, plan, defaults, what the model can do"]
    MF --> PV["Preview picture; trigger words from Civitai by the file's hash"]
```

- **Code is never downloaded** from a repository: pipelines come from the installed diffusers and transformers. A
  `.ckpt` is read as plain weights and stored as `.safetensors`.
- **Names**: an import gets the file's name, or the repository's when the file is called `model.safetensors` or the
  like.
- **Reuse**: a file with the same path and size in another imported model (a shared text encoder, for instance) is
  taken from there instead of being downloaded again.
- **At the first load** a single-file model whose base parts are missing gets them (from what is there, else
  downloaded once), an older FP8 import is converted to GGUF once, and a model that streams prepares its block cache
  once.
- **Recheck**: at the first start of a version with a better detection, all installed LoRAs and models are checked
  again offline; a wrong family or a missing sub-base is corrected, and each changed manifest is kept as `.bak`.

### <img src="icons/shield-check.svg" width="20" height="20" alt=""> Privacy in the pipelines

```mermaid
flowchart LR
    subgraph MAC["Stays on the Mac"]
        PR["Prompts, styles, settings"]
        PI["Input pictures, masks, poses, photos to restore"]
        RE["Results, History, Favorites"]
        TR["Training pictures and captions"]
        CF["ComfyUI, only on 127.0.0.1"]
    end
    subgraph NET["Uses the network"]
        RT["Runtimes, when installed: uv and ComfyUI checked by SHA-256"]
        MO["Models and LoRAs: Hugging Face, Civitai, with your token where stored"]
        HM["Helper models on first use: ControlNets, DWPose, Depth Anything, LaMa, DDColor, Real-ESRGAN, content check"]
        LF["LoRA finder: search words and base model, no token"]
        LI["LoRA descriptions and previews from their pages"]
        HS["Civitai lookup of a file by its SHA256: only when allowed in Settings → Privacy"]
    end
```

The engines compute everything on the Mac's GPU; no prompt, picture or result is ever sent anywhere. The network is
asked only for what is downloaded, for the LoRA finder and descriptions, for the daily update check of the runtimes
(public version lists; it can be switched off), and, only when allowed in *Settings → Privacy*, for the hash lookup
that finds a file's trigger words and base model on Civitai (it sends the file's checksum, not the file).

- The usage reports of the libraries are off (`HF_HUB_DISABLE_TELEMETRY`, `DO_NOT_TRACK`), and no Hugging Face login
  of the command line is used: a token goes only where the app passes the one stored in *Settings → Access tokens*.
- The MLX engine runs offline; ComfyUI runs offline, writes no prompt into its pictures and loads only the
  ComfyUI-GGUF extension.
- The content filter, LaMa and DDColor are fetched at a fixed commit and checked by their SHA-256; once there, they
  are used without asking Hugging Face again.
- The helper models (content filter, Restore, pose and depth, ControlNets, Real-ESRGAN, photo tools) are listed under
  *Models → Installed → Helpers* with a picture of what each does; they can be downloaded ahead or moved to the Trash,
  and every one is fetched at a fixed commit and checked by its SHA-256.
- Installing a runtime downloads uv at a fixed version and ComfyUI and its GGUF extension at a fixed release and
  commit, each checked by its SHA-256 before anything is installed. The packages themselves come from PyPI over
  HTTPS, within the version ranges of each engine's `requirements.txt` (so that **Update** can follow fixes).
- Folders are set only in the macOS folder dialog, and training pictures pass the content filter before a LoRA
  learns from them.
- A Civitai download link with `?token=…` loses the token before it is used, shown in a log or kept in a model's
  manifest. The LoRA finder asks only
Civitai and Hugging Face over HTTPS, and its preview pictures are fetched by the app itself, since the pages load
nothing from the internet.
