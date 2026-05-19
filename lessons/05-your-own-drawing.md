# Lesson 5 — Draw Your Own Character

**Goal:** replace the default blob with **your own pixel art** that
walks when your character walks.

You'll draw a tiny animation in a free online tool, export it as one
file, and drop it into the editor.

## Step 1 — Open PiskelApp

Go to [https://www.piskelapp.com/](https://www.piskelapp.com/) and
click **Create Sprite**.

A pixel-art editor opens. You don't need an account.

## Step 2 — Set the canvas size

On the right, set **Resize** to **32 × 32**. (Bigger = harder to draw,
slower to load. 32 is plenty for a small fighter.)

## Step 3 — Draw your character

- Use the **pencil** tool to colour pixels.
- Use the **eraser** to remove them.
- Pick colours from the palette on the bottom right.

Draw your character facing **down**. Keep the background empty (the
checkerboard pattern means "transparent").

## Step 4 — Add 3 more frames

On the left side, click **Add new frame** (the **+** at the bottom of
the frame list).

You want **4 frames total** that show the character walking — for
example, legs apart → together → apart the other way → together.

Tip: right-click a frame and pick **Duplicate** to copy a frame, then
edit it a little. Click **▶ Play** at the top to preview the animation.

> Only the **first 4 frames** are used. If you draw more, the extras
> are ignored.

## Step 5 — Export as a .c file

1. Click **Export** in the side bar.
2. Pick the **Other** tab.
3. Click **Download C file** (it makes a file like `mySprite.c`).
4. Save it somewhere you can find it.

## Step 6 — Drop it into your character

1. In the game editor, open the **🎨 Pixel art (PiskelApp)** panel
   above the code box.
2. Click **Choose file** and pick the `.c` file you just saved.
3. A preview of your 4 frames appears.
4. Click **↳ Insert into editor**.

The editor adds a `"sprites": { "walk": [ ... ] }` block to your
`build_character()` return dict. Don't worry about reading the long
strings — they're your pixels encoded as text.

## Step 7 — Run & Join

Click **Run & Validate**, then **Join match**. You should see your
own little drawing running around instead of the default blob.

## When it doesn't work

- **"Please upload a Piskel .c export."** → make sure the file ends in
  `.c`. PNG/GIF aren't supported here.
- **"frames total ... KB; keep your Piskel canvas small (max 64 KB)."**
  → your sprite is too big. Go back to Piskel and reduce the canvas
  size to 32×32 (or smaller), then re-export.
- **No frames in .c file** → you only had 1 frame. Add 3 more in
  Piskel and re-export.
- **It still looks like the default blob** → did you click **Insert
  into editor** *and* **Run & Validate** after?

## Done!

You drew your own character. Want to keep going? Try giving it a
totally new colour theme to match the drawing, or pair it with a
matching power (a fire-coloured character with a fireball, etc.).

← Back to [Lessons](README.md)
