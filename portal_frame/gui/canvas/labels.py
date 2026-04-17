"""Canvas labels -- draggable text, boxed labels, collision resolution."""

import math

from portal_frame.gui.theme import COLORS, FONT_SMALL


def _envelope_label_parts(is_envelope: bool, is_min: bool) -> tuple[str, str]:
    """Return (text_prefix, label_key_suffix) for envelope max/min peak labels."""
    if not is_envelope:
        return "", ""
    return ("min: ", "_min") if is_min else ("max: ", "")


def make_draggable(canvas, item_id, label_key):
    """Bind drag events to a canvas text item."""
    canvas.tag_bind(item_id, "<ButtonPress-1>", lambda e: canvas._drag_start(e, item_id, label_key))
    canvas.tag_bind(item_id, "<B1-Motion>", canvas._drag_move)
    canvas.tag_bind(item_id, "<ButtonRelease-1>", canvas._drag_end)
    canvas.tag_bind(item_id, "<Enter>", lambda e: canvas.config(cursor="fleur"))
    canvas.tag_bind(item_id, "<Leave>", lambda e: canvas.config(cursor=""))


def drag_start(canvas, event, item_id, label_key):
    canvas._drag_item = item_id
    canvas._drag_label_key = label_key
    ix, iy = canvas.coords(item_id)
    canvas._drag_offset = (event.x - ix, event.y - iy)


def drag_move(canvas, event):
    if canvas._drag_item is None:
        return
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    # Clamp within canvas
    nx = max(5, min(event.x - canvas._drag_offset[0], w - 5))
    ny = max(5, min(event.y - canvas._drag_offset[1], h - 5))
    # Compute delta from the current position so partners move by the
    # same amount (can't just set their coords -- they may be rects
    # with 4-tuple geometry rather than 2-tuple like text items).
    old_x, old_y = canvas.coords(canvas._drag_item)
    canvas.coords(canvas._drag_item, nx, ny)
    dx = nx - old_x
    dy = ny - old_y
    for partner in canvas._label_partners.get(canvas._drag_item, ()):
        canvas.move(partner, dx, dy)


def drag_end(canvas, event):
    if canvas._drag_item is None:
        return
    # Store the user offset so it persists across redraws
    cx, cy = canvas.coords(canvas._drag_item)
    key = canvas._drag_label_key
    if key and key in canvas._label_positions:
        ox, oy = canvas._label_positions[key]
        canvas._label_offsets[key] = (cx - ox, cy - oy)
    canvas._drag_item = None


def create_label(canvas, x, y, text, label_key, fill=None, font=None,
                 anchor="center", justify="center"):
    """Create a text label that is draggable and tracked for collision."""
    if fill is None:
        fill = COLORS["fg_dim"]
    if font is None:
        font = FONT_SMALL

    # Apply user offset if they previously dragged this label
    ux, uy = canvas._label_offsets.get(label_key, (0, 0))
    fx, fy = x + ux, y + uy

    # Clamp within canvas
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    fx = max(5, min(fx, w - 5))
    fy = max(8, min(fy, h - 8))

    item = canvas.create_text(fx, fy, text=text, fill=fill, font=font,
                              anchor=anchor, justify=justify, tags=("label",))
    make_draggable(canvas, item, label_key)
    # Store original (un-offset) position for drag delta calculation
    canvas._label_positions[label_key] = (x, y)
    canvas._label_items.append(item)
    canvas._item_to_key[item] = label_key
    return item


def create_boxed_draggable_label(
    canvas, x: float, y: float, text: str, label_key: str,
    fg: str, outline: str | None = None,
    bg: str | None = None, anchor: str = "center",
    bbox_pad: int = 3,
) -> int:
    """Create a text label with a background rect that drags as a unit.

    Uses the existing ``create_label`` infrastructure for the text item
    (so offsets persist across redraws), then draws a background rect
    around the final text position and registers the rect as a
    "partner" of the text so dragging either piece moves both.

    Also binds drag handlers on the rect so clicking the rect
    initiates a drag of the text (with the partner following).

    Returns the text item id.
    """
    if outline is None:
        outline = fg
    if bg is None:
        bg = COLORS["canvas_bg"]

    text_id = create_label(canvas, x, y, text, label_key, fill=fg, anchor=anchor)

    # bbox() needs the item to be laid out -- update_idletasks not
    # required since create_text is immediate, but bbox may be None
    # for very early draws with unmapped canvases. Guard for safety.
    bb = canvas.bbox(text_id)
    if bb is None:
        return text_id
    rect_id = canvas.create_rectangle(
        bb[0] - bbox_pad, bb[1] - bbox_pad,
        bb[2] + bbox_pad, bb[3] + bbox_pad,
        fill=bg, outline=outline, width=1,
        tags=("label", "label_bg"),
    )
    # Text must stay above its own background rect. Raise the text
    # explicitly after creating the rect (the rect was just drawn
    # so it's currently on top by default).
    canvas.tag_raise(text_id)

    # Register rect as a partner that moves with the text.
    canvas._label_partners.setdefault(text_id, []).append(rect_id)

    # Clicking the rect border should also start a drag of the text.
    canvas.tag_bind(rect_id, "<ButtonPress-1>",
        lambda e, tid=text_id, key=label_key: canvas._drag_start(e, tid, key))
    canvas.tag_bind(rect_id, "<B1-Motion>", canvas._drag_move)
    canvas.tag_bind(rect_id, "<ButtonRelease-1>", canvas._drag_end)
    canvas.tag_bind(rect_id, "<Enter>", lambda e: canvas.config(cursor="fleur"))
    canvas.tag_bind(rect_id, "<Leave>", lambda e: canvas.config(cursor=""))

    return text_id


def resolve_overlaps(canvas):
    """Nudge auto-placed labels that overlap. User-dragged labels are not moved."""
    canvas.update_idletasks()  # ensure bbox() returns valid geometry
    for _ in range(canvas.NUDGE_MAX_PASSES):
        moved = False
        items = list(canvas._label_items)
        bboxes = {}
        for item in items:
            bb = canvas.bbox(item)
            if bb:
                bboxes[item] = bb

        for i, a in enumerate(items):
            if a not in bboxes:
                continue
            ax1, ay1, ax2, ay2 = bboxes[a]
            p = canvas.LABEL_PAD
            for b in items[i+1:]:
                if b not in bboxes:
                    continue
                # Skip nudging labels the user has manually dragged
                b_key = canvas._item_to_key.get(b)
                if b_key and b_key in canvas._label_offsets:
                    continue
                bx1, by1, bx2, by2 = bboxes[b]
                if (ax1 - p < bx2 + p and ax2 + p > bx1 - p and
                        ay1 - p < by2 + p and ay2 + p > by1 - p):
                    cx_a = (ax1 + ax2) / 2
                    cy_a = (ay1 + ay2) / 2
                    cx_b = (bx1 + bx2) / 2
                    cy_b = (by1 + by2) / 2
                    dx = cx_b - cx_a
                    dy = cy_b - cy_a
                    dist = math.hypot(dx, dy)
                    if dist < 1:
                        dx, dy = 0, 1
                        dist = 1
                    nx = dx / dist * canvas.NUDGE_STEP
                    ny = dy / dist * canvas.NUDGE_STEP
                    canvas.move(b, nx, ny)
                    bboxes[b] = canvas.bbox(b)
                    moved = True
        if not moved:
            break
    # Final clamp: ensure all labels stay within canvas
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    for item in canvas._label_items:
        bb = canvas.bbox(item)
        if not bb:
            continue
        x1, y1, x2, y2 = bb
        shift_x = 0
        shift_y = 0
        if x1 < 2:
            shift_x = 2 - x1
        elif x2 > w - 2:
            shift_x = (w - 2) - x2
        if y1 < 2:
            shift_y = 2 - y1
        elif y2 > h - 2:
            shift_y = (h - 2) - y2
        if shift_x or shift_y:
            canvas.move(item, shift_x, shift_y)
